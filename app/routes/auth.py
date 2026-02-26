"""Rotas de autenticação: login e logout."""
import logging
from datetime import datetime
from flask import render_template, request, redirect, url_for, Response, session
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
    # Remove last_activity de sessão antiga para evitar "desconectado por inatividade"
    # na primeira requisição após login (quando o cookie ainda tinha timestamp antigo).
    if not current_user.is_authenticated:
        session.pop('last_activity', None)

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
            
            # Verificar se precisa trocar senha (exceto admins)
            if usuario.must_change_password and usuario.perfil != 'admin':
                logger.info(f"Redirecionando {usuario.email} para troca de senha obrigatória")
                flash_t('password_change_required_alert', 'warning')
                return redirect(url_for('main.alterar_senha_obrigatoria'))
            
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
                logger.info(f"Senha alterada com sucesso no primeiro acesso: {current_user.email}")
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
