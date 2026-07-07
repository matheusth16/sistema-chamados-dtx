"""Rotas de autenticação: login, logout e verificação de MFA."""

import logging
import threading
import uuid
from datetime import UTC, datetime

from flask import Response, current_app, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.cache import cache_delete
from app.i18n import flash_t
from app.limiter import limiter
from app.models_usuario import CACHE_KEY_USUARIOS, Usuario
from app.routes import main
from app.services import mfa_service, sso_microsoft_service
from app.services.login_attempts import LOCKOUT_DURATION, MAX_LOGIN_ATTEMPTS, LoginAttemptTracker
from app.services.notifications import notificar_admins_novo_usuario_sso, notificar_novo_usuario_sso
from app.services.notify_retry import executar_com_retry
from app.utils import get_client_ip, mask_email_for_log

logger = logging.getLogger(__name__)

# ── MFA: dispositivo confiável (cookie assinado) e estado pendente na sessão ────
MFA_TRUSTED_DEVICE_COOKIE = "dtx_mfa_trusted"
MFA_TRUSTED_DEVICE_MAX_AGE = 2592000  # 30 dias
MFA_TRUSTED_DEVICE_SALT = "mfa-trusted-device"
MFA_PENDING_TTL = 300  # 5 minutos para completar a verificação após a senha


def _serializer_dispositivo_confiavel() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt=MFA_TRUSTED_DEVICE_SALT)


def _dispositivo_confiavel(usuario_id: str) -> bool:
    """True se o cookie assinado de dispositivo confiável pertence a este usuário e não expirou."""
    token = request.cookies.get(MFA_TRUSTED_DEVICE_COOKIE)
    if not token:
        return False
    try:
        valor = _serializer_dispositivo_confiavel().loads(token, max_age=MFA_TRUSTED_DEVICE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return valor == usuario_id


def _marcar_dispositivo_confiavel(response: Response, usuario_id: str) -> None:
    """Grava cookie assinado marcando este dispositivo como confiável por 30 dias."""
    token = _serializer_dispositivo_confiavel().dumps(usuario_id)
    response.set_cookie(
        MFA_TRUSTED_DEVICE_COOKIE,
        token,
        max_age=MFA_TRUSTED_DEVICE_MAX_AGE,
        httponly=True,
        secure=bool(current_app.config.get("SESSION_COOKIE_SECURE", False)),
        samesite="Lax",
    )


def _limpar_mfa_pendente() -> None:
    session.pop("mfa_pendente_user_id", None)
    session.pop("mfa_pendente_remember", None)
    session.pop("mfa_pendente_ts", None)


def _finalizar_login(usuario: Usuario, remember: bool, client_ip: str) -> Response:
    """Conclui o login (sessão Flask-Login) após senha — e MFA, se aplicável — validados."""
    login_user(usuario, remember=remember, duration=None if remember else None)
    LoginAttemptTracker.log_success_attempt(usuario.email, client_ip, usuario.perfil)

    # Verificar se precisa trocar senha (exceto admins)
    if usuario.must_change_password and usuario.perfil != "admin":
        logger.info(
            "Redirecionando %s para troca de senha obrigatória",
            mask_email_for_log(usuario.email),
        )
        flash_t("password_change_required_alert", "warning")
        return redirect(url_for("main.alterar_senha_obrigatoria"))

    # MFA obrigatório para todos os perfis: sem ele configurado, não acessa mais nada
    if usuario.mfa_enabled is not True:
        logger.info(
            "Redirecionando %s para configuração obrigatória de MFA",
            mask_email_for_log(usuario.email),
        )
        flash_t("mfa_setup_required_alert", "warning")
        return redirect(url_for("main.mfa_configurar"))

    flash_t("welcome_user", "success", nome=usuario.nome)
    if usuario.perfil == "solicitante":
        return redirect(url_for("main.index"))
    if usuario.perfil == "supervisor":
        # Gestor read-only vai direto para o painel gerencial
        if getattr(usuario, "is_gestor", False) and not getattr(
            usuario, "is_admin_or_above", False
        ):
            return redirect(url_for("main.gestor_dashboard"))
        return redirect(url_for("main.painel"))
    return redirect(url_for("main.admin"))


@main.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login() -> Response:
    """GET: formulário de login. POST: valida credenciais e cria sessão."""
    # Remove last_activity de sessão antiga para evitar "desconectado por inatividade"
    # na primeira requisição após login (quando o cookie ainda tinha timestamp antigo).
    if not current_user.is_authenticated:
        session.pop("last_activity", None)

    if current_user.is_authenticated:
        logger.info(
            "Usuário %s (%s) já autenticado, redirecionando...",
            mask_email_for_log(current_user.email),
            current_user.perfil,
        )
        if current_user.perfil == "solicitante":
            return redirect(url_for("main.index"))
        if current_user.perfil == "supervisor":
            return redirect(url_for("main.painel"))
        return redirect(url_for("main.admin"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        client_ip = get_client_ip()

        if not email or not senha:
            flash_t("email_password_required", "danger")
            return redirect(url_for("main.login"))

        # Verifica se o IP está bloqueado
        if LoginAttemptTracker.is_locked_out(client_ip):
            flash_t(
                "login_temporarily_blocked",
                "danger",
                duration=LOCKOUT_DURATION // 60,
            )
            logger.warning(
                "Tentativa de login em IP bloqueado: %s (email: %s)",
                client_ip,
                mask_email_for_log(email),
            )
            return redirect(url_for("main.login"))

        # Verifica se o email está bloqueado (lockout por credencial)
        if LoginAttemptTracker.is_locked_out(email):
            flash_t(
                "login_temporarily_blocked",
                "danger",
                duration=LOCKOUT_DURATION // 60,
            )
            logger.warning(
                "Tentativa de login em email bloqueado: %s (IP: %s)",
                mask_email_for_log(email),
                client_ip,
            )
            return redirect(url_for("main.login"))

        usuario = Usuario.get_by_email(email)
        if usuario and usuario.check_password(senha):
            # Conta desativada: bloqueia antes de criar sessão; NÃO incrementa lockout
            if not getattr(usuario, "ativo", True):
                logger.warning("Login bloqueado: conta desativada %s", mask_email_for_log(email))
                flash_t("account_disabled", "danger")
                return redirect(url_for("main.login"))

            # Login bem-sucedido: reseta tentativas
            LoginAttemptTracker.reset_attempts(client_ip)
            LoginAttemptTracker.reset_attempts(email)

            # Verifica se o usuário selecionou "manter-me conectado"
            remember = request.form.get("remember-me") == "on"

            # MFA habilitado e dispositivo não é confiável: exige segundo fator
            if usuario.mfa_enabled is True and not _dispositivo_confiavel(usuario.id):
                session["mfa_pendente_user_id"] = usuario.id
                session["mfa_pendente_remember"] = remember
                session["mfa_pendente_ts"] = datetime.now(UTC).timestamp()
                logger.info("MFA pendente para %s", mask_email_for_log(usuario.email))
                return redirect(url_for("main.verificar_mfa"))

            # Se remember=True, cria persistent cookie válido por 30 dias
            # Se remember=False, cria session cookie que expira ao fechar navegador
            return _finalizar_login(usuario, remember, client_ip)

        # Login falhou: incrementa tentativas por IP e por email
        attempts = LoginAttemptTracker.increment_attempt(client_ip)
        attempts_email = LoginAttemptTracker.increment_attempt(email)
        LoginAttemptTracker.log_failed_attempt(email, client_ip, "credenciais inválidas")

        # Aplica lockout por IP se limite atingido
        if attempts >= MAX_LOGIN_ATTEMPTS:
            LoginAttemptTracker.apply_lockout(client_ip)
            logger.error(
                "Bloqueio por IP ativado após %d tentativas falhas: %s",
                attempts,
                client_ip,
            )
        # Aplica lockout por email se limite atingido
        if attempts_email >= MAX_LOGIN_ATTEMPTS:
            LoginAttemptTracker.apply_lockout(email)
            logger.error(
                "Bloqueio por email ativado após %d tentativas falhas: %s",
                attempts_email,
                mask_email_for_log(email),
            )
        if attempts >= MAX_LOGIN_ATTEMPTS or attempts_email >= MAX_LOGIN_ATTEMPTS:
            flash_t(
                "too_many_login_attempts",
                "danger",
                duration=LOCKOUT_DURATION // 60,
            )
            return redirect(url_for("main.login"))

        flash_t("invalid_email_password", "danger")
        return redirect(url_for("main.login"))

    return render_template("login.html")


def _auto_provisionar_usuario_sso(email: str, nome: str) -> Usuario:
    """Cria conta 'solicitante' (menor privilégio) no primeiro login via Microsoft.

    Sem senha local (senha_hash fica None) — check_password() já trata isso com
    segurança, então essa conta só pode entrar pelo botão "Entrar com Microsoft".
    """
    usuario = Usuario(
        id=f"user_{uuid.uuid4().hex}",
        email=email,
        nome=nome or email.split("@")[0],
        perfil="solicitante",
        must_change_password=False,
    )
    usuario.auth_provider = "microsoft"
    usuario.save()
    cache_delete(CACHE_KEY_USUARIOS)
    logger.info("Usuário auto-provisionado via SSO Microsoft: %s", mask_email_for_log(email))

    _app = current_app._get_current_object()

    def _notificar():
        with _app.app_context():
            executar_com_retry(
                notificar_novo_usuario_sso,
                usuario_id=usuario.id,
                usuario_email=usuario.email,
                usuario_nome=usuario.nome,
            )
            admins = [
                u.email
                for u in Usuario.get_all()
                if u.perfil in ("admin", "admin_global") and getattr(u, "ativo", True)
            ]
            if admins:
                executar_com_retry(
                    notificar_admins_novo_usuario_sso,
                    admin_emails=admins,
                    usuario_email=usuario.email,
                    usuario_nome=usuario.nome,
                )

    threading.Thread(target=_notificar, daemon=True).start()
    return usuario


@main.route("/login/microsoft")
@limiter.limit("10 per minute")
def login_microsoft() -> Response:
    """Redireciona para a tela de login da Microsoft (Authorization Code + PKCE)."""
    if not current_app.config.get("SSO_MICROSOFT_ENABLED", True):
        flash_t("sso_disabled", "warning")
        return redirect(url_for("main.login"))
    auth_uri, flow = sso_microsoft_service.iniciar_fluxo_login()
    session["sso_flow"] = flow
    return redirect(auth_uri)


@main.route("/login/microsoft/callback")
@limiter.limit("10 per minute")
def login_microsoft_callback() -> Response:
    """Callback do Microsoft Entra ID: valida state/PKCE/tenant e finaliza o login."""
    if not current_app.config.get("SSO_MICROSOFT_ENABLED", True):
        flash_t("sso_disabled", "warning")
        return redirect(url_for("main.login"))

    flow = session.pop("sso_flow", None)
    if not flow:
        flash_t("sso_login_failed", "danger")
        return redirect(url_for("main.login"))

    if request.args.get("error"):
        logger.warning("Erro retornado pela Microsoft no SSO: %s", request.args.get("error"))
        flash_t("sso_login_failed", "danger")
        return redirect(url_for("main.login"))

    result = sso_microsoft_service.concluir_fluxo_login(flow, request.args.to_dict())
    if "error" in result:
        logger.warning(
            "Falha ao obter token Microsoft: %s", result.get("error_description", result["error"])
        )
        flash_t("sso_login_failed", "danger")
        return redirect(url_for("main.login"))

    claims = result.get("id_token_claims", {})
    if not sso_microsoft_service.validar_tenant(claims):
        logger.warning("SSO rejeitado: tenant (tid) não corresponde ao tenant DTX")
        flash_t("sso_tenant_not_allowed", "danger")
        return redirect(url_for("main.login"))

    email, nome = sso_microsoft_service.extrair_identidade(claims)
    client_ip = get_client_ip()

    usuario = Usuario.get_by_email(email)
    if usuario is None:
        usuario = _auto_provisionar_usuario_sso(email, nome)
    elif not getattr(usuario, "ativo", True):
        logger.warning("Login SSO bloqueado: conta desativada %s", mask_email_for_log(email))
        flash_t("account_disabled", "danger")
        return redirect(url_for("main.login"))

    LoginAttemptTracker.reset_attempts(client_ip)
    LoginAttemptTracker.reset_attempts(email)
    return _finalizar_login(usuario, remember=False, client_ip=client_ip)


@main.route("/verificar-mfa", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def verificar_mfa() -> Response:
    """Segunda etapa do login: valida código TOTP ou código de backup."""
    pendente_id = session.get("mfa_pendente_user_id")
    pendente_ts = session.get("mfa_pendente_ts")

    if not pendente_id or not pendente_ts:
        return redirect(url_for("main.login"))

    if datetime.now(UTC).timestamp() - pendente_ts > MFA_PENDING_TTL:
        _limpar_mfa_pendente()
        flash_t("mfa_session_expired", "warning")
        return redirect(url_for("main.login"))

    if request.method == "POST":
        identificador = f"mfa:{pendente_id}"
        client_ip = get_client_ip()

        if LoginAttemptTracker.is_locked_out(identificador):
            _limpar_mfa_pendente()
            flash_t("login_temporarily_blocked", "danger", duration=LOCKOUT_DURATION // 60)
            return redirect(url_for("main.login"))

        usuario = Usuario.get_by_id(pendente_id)
        if not usuario or not getattr(usuario, "ativo", True) or usuario.mfa_enabled is not True:
            _limpar_mfa_pendente()
            flash_t("mfa_session_expired", "warning")
            return redirect(url_for("main.login"))

        codigo = request.form.get("codigo", "").strip()
        valido = mfa_service.verificar_codigo_totp(usuario.mfa_secret, codigo)

        if not valido:
            valido, restantes = mfa_service.verificar_e_consumir_codigo_backup(
                usuario.mfa_backup_codes, codigo
            )
            if valido:
                usuario.update(mfa_backup_codes=restantes)
                logger.info("Código de backup MFA consumido: %s", mask_email_for_log(usuario.email))

        if valido:
            LoginAttemptTracker.reset_attempts(identificador)
            remember = bool(session.get("mfa_pendente_remember"))
            _limpar_mfa_pendente()
            resposta = _finalizar_login(usuario, remember, client_ip)
            if request.form.get("confiar-dispositivo") == "on":
                _marcar_dispositivo_confiavel(resposta, usuario.id)
            return resposta

        tentativas = LoginAttemptTracker.increment_attempt(identificador)
        logger.warning("Código MFA inválido para %s", mask_email_for_log(usuario.email))
        if tentativas >= MAX_LOGIN_ATTEMPTS:
            LoginAttemptTracker.apply_lockout(identificador)
            _limpar_mfa_pendente()
            flash_t("login_temporarily_blocked", "danger", duration=LOCKOUT_DURATION // 60)
            return redirect(url_for("main.login"))

        flash_t("mfa_invalid_code", "danger")
        return redirect(url_for("main.verificar_mfa"))

    return render_template("verificar_mfa.html")


@main.route("/logout")
@login_required
def logout() -> Response:
    """Finaliza a sessão do usuário."""
    email = current_user.email
    logout_user()
    logger.info("Logout: %s", mask_email_for_log(email))
    flash_t("logout_success", "info")
    return redirect(url_for("main.login"))


@main.route("/meus-dados")
@login_required
def meus_dados() -> Response:
    """Autovisualização dos próprios dados pessoais (LGPD — direito de acesso)."""
    return render_template("meus_dados.html", usuario=current_user)


@main.route("/alterar-senha-obrigatoria", methods=["GET", "POST"])
@login_required
def alterar_senha_obrigatoria() -> Response:
    """Força o usuário a alterar a senha no primeiro acesso."""
    # Se o usuário já trocou a senha ou é admin, redireciona
    if not current_user.must_change_password or current_user.is_admin_or_above:
        if current_user.perfil == "solicitante":
            return redirect(url_for("main.index"))
        if current_user.perfil == "supervisor":
            return redirect(url_for("main.painel"))
        return redirect(url_for("main.admin"))

    if request.method == "POST":
        nova_senha = request.form.get("nova_senha", "").strip()
        confirmar_senha = request.form.get("confirmar_senha", "").strip()

        # Validações
        if not nova_senha or not confirmar_senha:
            flash_t("all_fields_required", "danger")
            return redirect(url_for("main.alterar_senha_obrigatoria"))

        if len(nova_senha) < 8:
            flash_t("password_min_8_chars", "danger")
            return redirect(url_for("main.alterar_senha_obrigatoria"))

        if not any(c.isalpha() for c in nova_senha) or not any(c.isdigit() for c in nova_senha):
            flash_t("password_must_have_letter_and_digit", "danger")
            return redirect(url_for("main.alterar_senha_obrigatoria"))

        if nova_senha != confirmar_senha:
            flash_t("passwords_must_match", "danger")
            return redirect(url_for("main.alterar_senha_obrigatoria"))

        # Atualizar senha
        try:
            sucesso = current_user.update(
                senha=nova_senha, must_change_password=False, password_changed_at=datetime.now()
            )

            if sucesso:
                logger.info(
                    "Senha alterada com sucesso no primeiro acesso: %s",
                    mask_email_for_log(current_user.email),
                )
                flash_t("password_changed_success", "success")

                # Redirecionar para o dashboard apropriado
                if current_user.perfil == "solicitante":
                    return redirect(url_for("main.index"))
                if current_user.perfil == "supervisor":
                    return redirect(url_for("main.painel"))
                return redirect(url_for("main.admin"))
            else:
                flash_t("error_updating_password", "danger")
                return redirect(url_for("main.alterar_senha_obrigatoria"))

        except Exception as e:
            logger.exception("Erro ao alterar senha: %s", e)
            flash_t("error_updating_password", "danger")
            return redirect(url_for("main.alterar_senha_obrigatoria"))

    return render_template("alterar_senha_obrigatoria.html")
