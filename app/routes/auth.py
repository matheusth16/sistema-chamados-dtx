"""Rotas de autenticação: login e logout."""
import logging
from datetime import datetime

from flask import Response, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.i18n import flash_t
from app.models_usuario import Usuario
from app.routes import main
from app.services.login_attempts import LOCKOUT_DURATION, MAX_LOGIN_ATTEMPTS, LoginAttemptTracker
from app.utils import get_client_ip, mask_email_for_log

logger = logging.getLogger(__name__)


@main.route('/login', methods=['GET', 'POST'])
def login() -> Response:
    """GET: formulário de login. POST: valida credenciais e cria sessão."""
    # Remove last_activity de sessão antiga para evitar "desconectado por inatividade"
    # na primeira requisição após login (quando o cookie ainda tinha timestamp antigo).
    if not current_user.is_authenticated:
        session.pop('last_activity', None)

    if current_user.is_authenticated:
        logger.info(
            "Usuário %s (%s) já autenticado, redirecionando...",
            mask_email_for_log(current_user.email),
            current_user.perfil,
        )
        if current_user.perfil == 'solicitante':
            return redirect(url_for('main.index'))
        return redirect(url_for('main.admin'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        senha = request.form.get('senha', '')
        client_ip = get_client_ip()

        if not email or not senha:
            flash_t('email_password_required', 'danger')
            return redirect(url_for('main.login'))

        # Verifica se o IP está bloqueado
        if LoginAttemptTracker.is_locked_out(client_ip):
            flash_t(
                'login_temporarily_blocked',
                'danger',
                duration=LOCKOUT_DURATION // 60  # Converte para minutos
            )
            logger.warning(
                "Tentativa de login em IP bloqueado: %s (email: %s)",
                client_ip,
                mask_email_for_log(email),
            )
            return redirect(url_for('main.login'))

        usuario = Usuario.get_by_email(email)
        if usuario and usuario.check_password(senha):
            # Login bem-sucedido: reseta tentativas
            LoginAttemptTracker.reset_attempts(client_ip)
            LoginAttemptTracker.reset_attempts(email)

            # Verifica se o usuário selecionou "manter-me conectado"
            remember = request.form.get('remember-me') == 'on'
            # Se remember=True, cria persistent cookie válido por 30 dias
            # Se remember=False, cria session cookie que expira ao fechar navegador
            login_user(usuario, remember=remember, duration=None if remember else None)
            LoginAttemptTracker.log_success_attempt(email, client_ip, usuario.perfil)

            # Verificar se precisa trocar senha (exceto admins)
            if usuario.must_change_password and usuario.perfil != 'admin':
                logger.info(
                    "Redirecionando %s para troca de senha obrigatória",
                    mask_email_for_log(usuario.email),
                )
                flash_t('password_change_required_alert', 'warning')
                return redirect(url_for('main.alterar_senha_obrigatoria'))

            flash_t('welcome_user', 'success', nome=usuario.nome)
            if usuario.perfil == 'solicitante':
                return redirect(url_for('main.index'))
            return redirect(url_for('main.admin'))

        # Login falhou: incrementa tentativas
        attempts = LoginAttemptTracker.increment_attempt(client_ip)
        LoginAttemptTracker.log_failed_attempt(email, client_ip, "credenciais inválidas")

        # Verifica se excedeu o limite de tentativas
        if attempts >= MAX_LOGIN_ATTEMPTS:
            LoginAttemptTracker.apply_lockout(client_ip)
            flash_t(
                'too_many_login_attempts',
                'danger',
                duration=LOCKOUT_DURATION // 60  # Converte para minutos
            )
            logger.error(
                "Bloqueio ativado após %d tentativas falhas do IP %s",
                attempts,
                client_ip,
            )
            return redirect(url_for('main.login'))

        flash_t('invalid_email_password', 'danger')
        return redirect(url_for('main.login'))

    return render_template('login.html')


@main.route('/logout')
@login_required
def logout() -> Response:
    """Finaliza a sessão do usuário."""
    email = current_user.email
    logout_user()
    logger.info("Logout: %s", mask_email_for_log(email))
    flash_t('logout_success', 'info')
    return redirect(url_for('main.login'))


@main.route('/alterar-senha-obrigatoria', methods=['GET', 'POST'])
@login_required
def alterar_senha_obrigatoria() -> Response:
    """Força o usuário a alterar a senha no primeiro acesso."""
    # Se o usuário já trocou a senha ou é admin, redireciona
    if not current_user.must_change_password or current_user.perfil == 'admin':
        if current_user.perfil == 'solicitante':
            return redirect(url_for('main.index'))
        return redirect(url_for('main.admin'))

    if request.method == 'POST':
        nova_senha = request.form.get('nova_senha', '').strip()
        confirmar_senha = request.form.get('confirmar_senha', '').strip()

        # Validações
        if not nova_senha or not confirmar_senha:
            flash_t('all_fields_required', 'danger')
            return redirect(url_for('main.alterar_senha_obrigatoria'))

        if len(nova_senha) < 6:
            flash_t('password_min_6_chars', 'danger')
            return redirect(url_for('main.alterar_senha_obrigatoria'))

        if nova_senha != confirmar_senha:
            flash_t('passwords_must_match', 'danger')
            return redirect(url_for('main.alterar_senha_obrigatoria'))

        # Verificar se a nova senha é diferente da senha padrão
        if nova_senha == '123456':
            flash_t('password_cannot_be_default', 'danger')
            return redirect(url_for('main.alterar_senha_obrigatoria'))

        # Atualizar senha
        try:
            sucesso = current_user.update(
                senha=nova_senha,
                must_change_password=False,
                password_changed_at=datetime.now()
            )

            if sucesso:
                logger.info(
                    "Senha alterada com sucesso no primeiro acesso: %s",
                    mask_email_for_log(current_user.email),
                )
                flash_t('password_changed_success', 'success')

                # Redirecionar para o dashboard apropriado
                if current_user.perfil == 'solicitante':
                    return redirect(url_for('main.index'))
                return redirect(url_for('main.admin'))
            else:
                flash_t('error_updating_password', 'danger')
                return redirect(url_for('main.alterar_senha_obrigatoria'))

        except Exception as e:
            logger.exception(f"Erro ao alterar senha: {e}")
            flash_t('error_updating_password', 'danger')
            return redirect(url_for('main.alterar_senha_obrigatoria'))

    return render_template('alterar_senha_obrigatoria.html')
