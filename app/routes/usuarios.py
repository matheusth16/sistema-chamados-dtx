"""Rotas de gerenciamento de usuários (CRUD). Apenas para admins."""

import logging
import secrets
import string
import threading
import uuid

from flask import Response, current_app, redirect, render_template, request, url_for
from flask_login import current_user

from app.cache import cache_delete
from app.decoradores import requer_perfil
from app.i18n import flash_t
from app.models_categorias import CategoriaSetor
from app.models_usuario import CACHE_KEY_USUARIOS, Usuario
from app.routes import main
from app.services.historico_usuario_service import registrar_historico_usuario
from app.services.notifications import notificar_mudanca_perfil, notificar_novo_usuario_cadastrado
from app.services.notify_retry import executar_com_retry

DOMINIO_EMAIL_PERMITIDO = "@dtx.aero"

# Contas de admin raiz protegidas contra exclusão/desativação/anonimização —
# nunca ficam sem pelo menos um admin_global de acesso garantido ao sistema.
EMAILS_ADMIN_RAIZ_PROTEGIDOS = frozenset({"matheus.costa@dtx.aero", "admin@dtx.aero"})

logger = logging.getLogger(__name__)


def _bloquear_se_admin_raiz(usuario: Usuario, usuario_id: str, translation_key: str, acao: str):
    """Bloqueia ação sobre um admin raiz protegido — exceto quando a própria conta age
    sobre si mesma (a proteção é contra terceiros, não contra auto-gerenciamento).

    Retorna a Response de redirect se bloqueado, ou None se a ação pode prosseguir.
    """
    if usuario.email in EMAILS_ADMIN_RAIZ_PROTEGIDOS and usuario_id != current_user.id:
        flash_t(translation_key, "danger")
        logger.warning(
            "Tentativa de %s admin raiz protegido (%s) por %s",
            acao,
            usuario.email,
            current_user.email,
        )
        return redirect(url_for("main.gerenciar_usuarios"))
    return None


def _gerar_senha_aleatoria(tamanho: int = 12) -> str:
    """Gera senha aleatória segura com maiúsculas, minúsculas, dígitos e símbolos.
    Garante ao menos 1 char de cada classe para satisfazer políticas de complexidade."""
    especiais = "!@#$%&*"
    alfabeto = string.ascii_letters + string.digits + especiais
    # Posições fixas garantem representação mínima de cada classe
    obrigatorios = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(especiais),
    ]
    restante = [secrets.choice(alfabeto) for _ in range(tamanho - 4)]
    senha = obrigatorios + restante
    secrets.SystemRandom().shuffle(senha)
    return "".join(senha)


@main.route("/admin/usuarios", methods=["GET", "POST"])
@requer_perfil("admin")
def gerenciar_usuarios() -> Response:
    """GET: lista usuários. POST: cria usuário."""
    if request.method == "POST" and request.form.get("acao") == "criar":
        email = request.form.get("email", "").strip().lower()
        nome = request.form.get("nome", "").strip()
        perfil = request.form.get("perfil", "solicitante")
        areas = [a.strip() for a in request.form.getlist("areas") if a.strip()]
        nivel_gestao = request.form.get("nivel_gestao", "").strip() or None
        erros = []
        if not email or "@" not in email:
            erros.append("invalid_email")
        elif not email.endswith(DOMINIO_EMAIL_PERMITIDO):
            erros.append("invalid_email_domain")
        elif Usuario.email_existe(email):
            erros.append("email_exists")
        if not nome or len(nome) < 3:
            erros.append("name_min_chars")
        if perfil not in ["solicitante", "supervisor", "admin"]:
            erros.append("invalid_profile")
        if perfil == "supervisor" and not areas:
            erros.append("area_required_for_supervisor")
        # Sub-admins não podem criar outros admins — apenas admin_global pode
        if perfil == "admin" and current_user.perfil != "admin_global":
            erros.append("access_denied_create_admin")
        if erros:
            for e in erros:
                flash_t(e, "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        try:
            senha_inicial = _gerar_senha_aleatoria()
            u = Usuario(
                id=f"user_{uuid.uuid4().hex}",
                email=email,
                nome=nome,
                perfil=perfil,
                areas=areas,
                nivel_gestao=nivel_gestao,
                must_change_password=True,
                password_changed_at=None,
            )
            u.set_password(senha_inicial)
            u.save()
            cache_delete(CACHE_KEY_USUARIOS)
            Usuario.invalidar_cache_supervisores_por_area()
            registrar_historico_usuario(
                usuario_alvo_id=u.id,
                usuario_alvo_nome=u.nome,
                admin_id=current_user.id,
                admin_nome=current_user.nome,
                acao="criacao",
                detalhe=f"perfil={perfil}",
            )

            _app = current_app._get_current_object()

            def _notificar_novo_usuario():
                with _app.app_context():
                    executar_com_retry(
                        notificar_novo_usuario_cadastrado,
                        usuario_id=u.id,
                        usuario_email=u.email,
                        usuario_nome=u.nome,
                        perfil=u.perfil,
                        areas=u.areas,
                        senha_inicial=senha_inicial,
                    )

            threading.Thread(target=_notificar_novo_usuario, daemon=True).start()
            flash_t("user_created_success", "success", nome=nome)
            return redirect(url_for("main.gerenciar_usuarios"))
        except Exception as e:
            logger.exception("Erro ao criar usuário: %s", e)
            flash_t("error_creating_user", "danger", error=str(e))
            return redirect(url_for("main.gerenciar_usuarios"))
    try:
        from app.services.lgpd_self_service import listar_usuarios_com_solicitacao_pendente

        usuarios = Usuario.get_all()
        ids_com_solicitacao_lgpd = listar_usuarios_com_solicitacao_pendente()
        return render_template(
            "usuarios.html", usuarios=usuarios, ids_com_solicitacao_lgpd=ids_com_solicitacao_lgpd
        )
    except Exception as e:
        logger.exception("Erro ao listar usuários: %s", e)
        flash_t("error_loading_users", "danger")
        return redirect(url_for("main.admin"))  # lista de usuários é exclusiva do admin


@main.route("/admin/usuarios/novo", methods=["GET"])
@requer_perfil("admin")
def novo_usuario_form() -> Response:
    """Exibe formulário de criação de usuário."""
    setores = [s for s in CategoriaSetor.get_all() if getattr(s, "ativo", True)]
    return render_template("usuario_form.html", usuario=None, setores=setores)


@main.route("/admin/usuarios/<usuario_id>/editar", methods=["GET", "POST"])
@requer_perfil("admin")
def editar_usuario(usuario_id: str) -> Response:
    """GET: exibe formulário de edição. POST: edita usuário."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t("user_not_found", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        if usuario.perfil == "admin_global" and current_user.perfil != "admin_global":
            flash_t("cannot_edit_admin_global", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        bloqueio = _bloquear_se_admin_raiz(usuario, usuario_id, "cannot_edit_root_admin", "editar")
        if bloqueio:
            return bloqueio
        if request.method == "GET":
            setores = [s for s in CategoriaSetor.get_all() if getattr(s, "ativo", True)]
            setor_names = {s.nome_pt for s in setores}
            areas_usuario = usuario.areas if getattr(usuario, "areas", None) else []
            areas_extra = [a for a in areas_usuario if a and a not in setor_names]
            return render_template(
                "usuario_form.html", usuario=usuario, setores=setores, areas_extra=areas_extra
            )
        email = request.form.get("email", "").strip().lower()
        nome = request.form.get("nome", "").strip()
        perfil_original = usuario.perfil
        perfil = request.form.get("perfil", usuario.perfil)
        areas = [a.strip() for a in request.form.getlist("areas") if a.strip()]
        erros = []
        if email and email != usuario.email:
            if "@" not in email:
                erros.append("invalid_email")
            elif not email.endswith(DOMINIO_EMAIL_PERMITIDO):
                erros.append("invalid_email_domain")
            elif Usuario.email_existe(email, usuario_id):
                erros.append("email_exists")
        if not nome or len(nome) < 3:
            erros.append("name_min_chars")
        if perfil not in ["solicitante", "supervisor", "admin"]:
            erros.append("invalid_profile")
        if perfil == "supervisor" and not areas:
            erros.append("area_required_for_supervisor")
        # Sub-admins não podem promover para admin — apenas admin_global pode
        if perfil == "admin" and current_user.perfil != "admin_global":
            erros.append("access_denied_create_admin")
        if erros:
            for e in erros:
                flash_t(e, "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        update_data = {}
        if email and email != usuario.email:
            update_data["email"] = email
        if nome and nome != usuario.nome:
            update_data["nome"] = nome
        if perfil and perfil != usuario.perfil:
            update_data["perfil"] = perfil
        if set(areas) != set(usuario.areas):
            update_data["areas"] = areas
        # Checkbox ativo: presente no form → True; ausente → False
        novo_ativo = request.form.get("ativo") == "on"
        if novo_ativo != getattr(usuario, "ativo", True):
            update_data["ativo"] = novo_ativo
        # nivel_gestao: campo opcional select (vazio = None = sem gestão)
        novo_nivel_gestao = request.form.get("nivel_gestao", "").strip() or None
        if novo_nivel_gestao != getattr(usuario, "nivel_gestao", None):
            update_data["nivel_gestao"] = novo_nivel_gestao
        perfil_mudou = "perfil" in update_data and perfil != perfil_original
        # Perfil novo (nunca visto por essa conta) reinicia o tour — perfil
        # já visto antes (ex.: rebaixado de volta) não precisa ver de novo.
        if perfil_mudou and perfil not in (usuario.onboarding_perfis_vistos or []):
            update_data["onboarding_passo"] = 0
        if update_data:
            usuario.update(**update_data)
            cache_delete(CACHE_KEY_USUARIOS)
            cache_delete(f"usuario_{usuario_id}")
            Usuario.invalidar_cache_supervisores_por_area()
            registrar_historico_usuario(
                usuario_alvo_id=usuario_id,
                usuario_alvo_nome=nome or usuario.nome,
                admin_id=current_user.id,
                admin_nome=current_user.nome,
                acao="edicao",
                detalhe=f"campos={','.join(sorted(update_data.keys()))}",
            )

        if perfil_mudou:
            _app = current_app._get_current_object()
            email_notif = update_data.get("email", usuario.email)
            nome_notif = update_data.get("nome", usuario.nome)

            def _notificar_mudanca_perfil():
                with _app.app_context():
                    executar_com_retry(
                        notificar_mudanca_perfil,
                        usuario_email=email_notif,
                        usuario_nome=nome_notif,
                        novo_perfil=perfil,
                    )

            threading.Thread(target=_notificar_mudanca_perfil, daemon=True).start()

        flash_t("user_updated_success", "success", nome=nome)
        return redirect(url_for("main.gerenciar_usuarios"))
    except Exception as e:
        logger.exception("Erro ao editar usuário: %s", e)
        flash_t("error_editing_user", "danger", error=str(e))
        return redirect(url_for("main.gerenciar_usuarios"))


@main.route("/admin/usuarios/<usuario_id>/deletar", methods=["POST"])
@requer_perfil("admin")
def deletar_usuario(usuario_id: str) -> Response:
    """Deleta usuário (exceto admins raiz protegidos)."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t("user_not_found", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        if usuario_id == current_user.id:
            flash_t("cannot_delete_own_account", "warning")
            return redirect(url_for("main.gerenciar_usuarios"))
        if usuario.perfil == "admin_global" and current_user.perfil != "admin_global":
            flash_t("cannot_delete_admin_global", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        bloqueio = _bloquear_se_admin_raiz(
            usuario, usuario_id, "cannot_delete_root_admin", "deletar"
        )
        if bloqueio:
            return bloqueio
        nome_usuario = usuario.nome
        usuario.delete()
        cache_delete(CACHE_KEY_USUARIOS)
        cache_delete(f"usuario_{usuario_id}")
        Usuario.invalidar_cache_supervisores_por_area()
        registrar_historico_usuario(
            usuario_alvo_id=usuario_id,
            usuario_alvo_nome=nome_usuario,
            admin_id=current_user.id,
            admin_nome=current_user.nome,
            acao="exclusao",
        )
        flash_t("user_deleted_success", "success", nome=nome_usuario)
        return redirect(url_for("main.gerenciar_usuarios"))
    except Exception as e:
        logger.exception("Erro ao deletar usuário: %s", e)
        flash_t("error_deleting_user", "danger", error=str(e))
        return redirect(url_for("main.gerenciar_usuarios"))


@main.route("/admin/alterar-senha", methods=["GET", "POST"])
@requer_perfil("admin")
def alterar_senha_admin() -> Response:
    """GET: exibe formulário de troca de senha. POST: aplica nova senha ao próprio perfil."""
    from datetime import datetime

    if request.method == "POST":
        senha_atual = request.form.get("senha_atual", "").strip()
        nova_senha = request.form.get("nova_senha", "").strip()
        confirmar_senha = request.form.get("confirmar_senha", "").strip()

        if not senha_atual or not nova_senha or not confirmar_senha:
            flash_t("all_fields_required", "danger")
            return redirect(url_for("main.alterar_senha_admin"))

        if not current_user.check_password(senha_atual):
            flash_t("current_password_incorrect", "danger")
            return redirect(url_for("main.alterar_senha_admin"))

        if len(nova_senha) < 8:
            flash_t("password_min_8_chars", "danger")
            return redirect(url_for("main.alterar_senha_admin"))

        if not any(c.isalpha() for c in nova_senha) or not any(c.isdigit() for c in nova_senha):
            flash_t("password_must_have_letter_and_digit", "danger")
            return redirect(url_for("main.alterar_senha_admin"))

        if nova_senha != confirmar_senha:
            flash_t("passwords_must_match", "danger")
            return redirect(url_for("main.alterar_senha_admin"))

        try:
            sucesso = current_user.update(
                senha=nova_senha,
                must_change_password=False,
                password_changed_at=datetime.now(),
            )
            if sucesso:
                logger.info("Admin %s alterou a própria senha.", current_user.email)
                flash_t("password_changed_admin_success", "success")
            else:
                flash_t("error_updating_password", "danger")
        except Exception as e:
            logger.exception("Erro ao alterar senha do admin %s: %s", current_user.email, e)
            flash_t("error_updating_password", "danger")

        return redirect(url_for("main.alterar_senha_admin"))

    return render_template("alterar_senha_admin.html")


@main.route("/admin/usuarios/<usuario_id>/resetar-senha", methods=["POST"])
@requer_perfil("admin")
def resetar_senha_usuario(usuario_id: str) -> Response:
    """Reseta a senha de um usuário para uma senha aleatória e notifica por e-mail."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t("user_not_found", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))

        if usuario_id == current_user.id:
            flash_t("cannot_reset_own_password", "warning")
            return redirect(url_for("main.gerenciar_usuarios"))

        if usuario.perfil == "admin_global" and current_user.perfil != "admin_global":
            flash_t("cannot_reset_password_admin_global", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))

        nome_usuario = usuario.nome
        senha_inicial = _gerar_senha_aleatoria()
        usuario.update(senha=senha_inicial, must_change_password=True)

        cache_delete(CACHE_KEY_USUARIOS)
        cache_delete(f"usuario_{usuario_id}")

        logger.info(
            "Senha resetada para %s por %s",
            usuario.email,
            current_user.email,
        )

        _app = current_app._get_current_object()
        _u_email = usuario.email
        _u_nome = usuario.nome
        _u_perfil = usuario.perfil
        _u_areas = list(getattr(usuario, "areas", []) or [])
        _u_id = usuario.id

        def _notificar_reset():
            with _app.app_context():
                executar_com_retry(
                    notificar_novo_usuario_cadastrado,
                    usuario_id=_u_id,
                    usuario_email=_u_email,
                    usuario_nome=_u_nome,
                    perfil=_u_perfil,
                    areas=_u_areas,
                    senha_inicial=senha_inicial,
                )

        threading.Thread(target=_notificar_reset, daemon=True).start()

        flash_t("user_password_reset_success", "success", nome=nome_usuario)
        return redirect(url_for("main.gerenciar_usuarios"))

    except Exception as e:
        logger.exception("Erro ao resetar senha do usuário: %s", e)
        flash_t("error_resetting_password", "danger", error=str(e))
        return redirect(url_for("main.gerenciar_usuarios"))


@main.route("/admin/usuarios/<usuario_id>/desativar", methods=["POST"])
@requer_perfil("admin")
def desativar_usuario(usuario_id: str) -> Response:
    """Soft-delete: marca ativo=False, bloqueando login e invalidando sessão."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t("user_not_found", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        if usuario_id == current_user.id:
            flash_t("cannot_deactivate_own_account", "warning")
            return redirect(url_for("main.gerenciar_usuarios"))
        if usuario.perfil == "admin_global" and current_user.perfil != "admin_global":
            flash_t("cannot_deactivate_admin_global", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        bloqueio = _bloquear_se_admin_raiz(
            usuario, usuario_id, "cannot_deactivate_root_admin", "desativar"
        )
        if bloqueio:
            return bloqueio
        nome_usuario = usuario.nome
        usuario.update(ativo=False)
        cache_delete(CACHE_KEY_USUARIOS)
        cache_delete(f"usuario_{usuario_id}")
        Usuario.invalidar_cache_supervisores_por_area()
        registrar_historico_usuario(
            usuario_alvo_id=usuario_id,
            usuario_alvo_nome=nome_usuario,
            admin_id=current_user.id,
            admin_nome=current_user.nome,
            acao="desativacao",
        )
        flash_t("user_deactivated_success", "success", nome=nome_usuario)
        return redirect(url_for("main.gerenciar_usuarios"))
    except Exception as e:
        logger.exception("Erro ao desativar usuário: %s", e)
        flash_t("error_editing_user", "danger", error=str(e))
        return redirect(url_for("main.gerenciar_usuarios"))


@main.route("/admin/usuarios/<usuario_id>/ativar", methods=["POST"])
@requer_perfil("admin")
def ativar_usuario(usuario_id: str) -> Response:
    """Reativa conta: marca ativo=True, permitindo login novamente."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t("user_not_found", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        if usuario.perfil == "admin_global" and current_user.perfil != "admin_global":
            flash_t("cannot_activate_admin_global", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        nome_usuario = usuario.nome
        usuario.update(ativo=True)
        cache_delete(CACHE_KEY_USUARIOS)
        cache_delete(f"usuario_{usuario_id}")
        Usuario.invalidar_cache_supervisores_por_area()
        registrar_historico_usuario(
            usuario_alvo_id=usuario_id,
            usuario_alvo_nome=nome_usuario,
            admin_id=current_user.id,
            admin_nome=current_user.nome,
            acao="ativacao",
        )
        flash_t("user_activated_success", "success", nome=nome_usuario)
        return redirect(url_for("main.gerenciar_usuarios"))
    except Exception as e:
        logger.exception("Erro ao reativar usuário: %s", e)
        flash_t("error_editing_user", "danger", error=str(e))
        return redirect(url_for("main.gerenciar_usuarios"))


@main.route("/admin/usuarios/<usuario_id>/anonimizar", methods=["POST"])
@requer_perfil("admin")
def anonimizar_usuario(usuario_id: str) -> Response:
    """Anonimiza nome/email de um usuário já desativado (LGPD — ação irreversível, sob demanda).

    Só permitido para contas já desativadas (ativo=False): o soft-delete continua
    reversível; anonimizar é um passo separado e deliberado que o admin aciona
    quando quer de fato apagar os dados pessoais, não apenas bloquear o acesso.
    """
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t("user_not_found", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        if usuario_id == current_user.id:
            flash_t("cannot_anonymize_own_account", "warning")
            return redirect(url_for("main.gerenciar_usuarios"))
        if usuario.perfil == "admin_global" and current_user.perfil != "admin_global":
            flash_t("cannot_anonymize_admin_global", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        bloqueio = _bloquear_se_admin_raiz(
            usuario, usuario_id, "cannot_anonymize_root_admin", "anonimizar"
        )
        if bloqueio:
            return bloqueio
        if getattr(usuario, "ativo", True):
            flash_t("must_deactivate_before_anonymize", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))

        nome_anonimizado = "Usuário Removido"
        email_anonimizado = f"removido-{usuario_id}@anonimizado.invalid"
        usuario.update(nome=nome_anonimizado, email=email_anonimizado)
        cache_delete(CACHE_KEY_USUARIOS)
        cache_delete(f"usuario_{usuario_id}")
        Usuario.invalidar_cache_supervisores_por_area()
        registrar_historico_usuario(
            usuario_alvo_id=usuario_id,
            usuario_alvo_nome=nome_anonimizado,
            admin_id=current_user.id,
            admin_nome=current_user.nome,
            acao="anonimizacao",
        )
        flash_t("user_anonymized_success", "success")
        return redirect(url_for("main.gerenciar_usuarios"))
    except Exception as e:
        logger.exception("Erro ao anonimizar usuário: %s", e)
        flash_t("error_editing_user", "danger", error=str(e))
        return redirect(url_for("main.gerenciar_usuarios"))


@main.route("/admin/usuarios/<usuario_id>/desativar-mfa", methods=["POST"])
@requer_perfil("admin")
def desativar_mfa_usuario(usuario_id: str) -> Response:
    """Desativa o MFA de um usuário — válvula de escape para conta travada sem backup codes."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t("user_not_found", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        if usuario.perfil == "admin_global" and current_user.perfil != "admin_global":
            flash_t("cannot_edit_admin_global", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        nome_usuario = usuario.nome
        usuario.update(mfa_enabled=False, mfa_secret=None, mfa_backup_codes=None)
        logger.info(
            "MFA desativado por admin: usuário %s por %s", usuario.email, current_user.email
        )
        flash_t("user_mfa_disabled_success", "success", nome=nome_usuario)
        return redirect(url_for("main.gerenciar_usuarios"))
    except Exception as e:
        logger.exception("Erro ao desativar MFA do usuário: %s", e)
        flash_t("error_editing_user", "danger", error=str(e))
        return redirect(url_for("main.gerenciar_usuarios"))


@main.route("/admin/usuarios/<usuario_id>/reset-exp", methods=["POST"])
@requer_perfil("admin")
def resetar_exp_usuario(usuario_id: str) -> Response:
    """Zera a experiência e nível do usuário."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t("user_not_found", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))

        nome_usuario = usuario.nome
        usuario.update(
            gamification={"exp_total": 0, "exp_semanal": 0, "level": 1, "conquistas": []}
        )

        cache_delete(CACHE_KEY_USUARIOS)
        cache_delete(f"usuario_{usuario_id}")
        Usuario.invalidar_cache_supervisores_por_area()

        # Opcional: deletar cache do ranking
        cache_delete("ranking_gamificacao_semanal")

        flash_t("user_exp_reset_success", "success", nome=nome_usuario)
        return redirect(url_for("main.gerenciar_usuarios"))

    except Exception as e:
        logger.exception("Erro ao resetar EXP do usuário: %s", e)
        flash_t("error_resetting_exp", "danger", error=str(e))
        return redirect(url_for("main.gerenciar_usuarios"))
