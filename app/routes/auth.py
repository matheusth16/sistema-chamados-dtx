"""Rotas de autenticação: login e logout."""
import logging
from flask import render_template, request, redirect, url_for, Response
from flask_login import login_user, logout_user, current_user, login_required
from app.i18n import flash_t
from app.routes import main
from app.limiter import limiter
from app.models_usuario import Usuario

logger = logging.getLogger(__name__)


@main.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login() -> Response:
    """GET: formulário de login. POST: valida credenciais e cria sessão."""
    if current_user.is_authenticated:
        logger.info(f"Usuário {current_user.email} ({current_user.perfil}) já autenticado, redirecionando...")
        if current_user.perfil == 'solicitante':
            return redirect(url_for('main.index'))
        return redirect(url_for('main.admin'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        senha = request.form.get('senha', '')

        if not email or not senha:
            flash_t('email_password_required', 'danger')
            return redirect(url_for('main.login'))

        usuario = Usuario.get_by_email(email)
        if usuario and usuario.check_password(senha):
            # remember=False ensures it's a session cookie that expires on browser close
            login_user(usuario, remember=False)
            logger.info(f"Login bem-sucedido: {usuario.email} ({usuario.nome}, Perfil: {usuario.perfil})")
            flash_t('welcome_user', 'success', nome=usuario.nome)
            if usuario.perfil == 'solicitante':
                return redirect(url_for('main.index'))
            return redirect(url_for('main.admin'))

        logger.warning(f"Falha de autenticação: email {email} ou senha incorretos")
        flash_t('invalid_email_password', 'danger')
        return redirect(url_for('main.login'))

    return render_template('login.html')


@main.route('/logout')
@login_required
def logout() -> Response:
    """Finaliza a sessão do usuário."""
    email = current_user.email
    logout_user()
    logger.info(f"Logout: {email}")
    flash_t('logout_success', 'info')
    return redirect(url_for('main.login'))
