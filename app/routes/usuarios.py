"""Rotas de gerenciamento de usuários (CRUD). Apenas para admins."""
import logging

from flask import Response, redirect, render_template, request, url_for
from flask_login import current_user

from app.cache import cache_delete
from app.decoradores import requer_perfil
from app.i18n import flash_t
from app.models_usuario import CACHE_KEY_USUARIOS, Usuario
from app.routes import main

logger = logging.getLogger(__name__)


@main.route('/admin/usuarios', methods=['GET', 'POST'])
@requer_perfil('admin')
def gerenciar_usuarios() -> Response:
    """GET: lista usuários. POST: cria usuário."""
    if request.method == 'POST' and request.form.get('acao') == 'criar':
        email = request.form.get('email', '').strip().lower()
        nome = request.form.get('nome', '').strip()
        perfil = request.form.get('perfil', 'solicitante')
        areas = [a.strip() for a in request.form.getlist('areas') if a.strip()]
        erros = []
        if not email or '@' not in email:
            erros.append('invalid_email')
        elif Usuario.email_existe(email):
            erros.append('email_exists')
        if not nome or len(nome) < 3:
            erros.append('name_min_chars')
        if perfil not in ['solicitante', 'supervisor', 'admin']:
            erros.append('invalid_profile')
        if perfil == 'supervisor' and not areas:
            erros.append('area_required_for_supervisor')
        if erros:
            for e in erros:
                flash_t(e, 'danger')
            return redirect(url_for('main.gerenciar_usuarios'))
        try:
            u = Usuario(
                id=f"user_{email.split('@')[0]}_{hash(email) % 100000}",
                email=email,
                nome=nome,
                perfil=perfil,
                areas=areas,
                must_change_password=(perfil in ['solicitante', 'supervisor']),
                password_changed_at=None
            )
            u.set_password('123456')  # Senha padrão para todos os novos usuários
            u.save()
            cache_delete(CACHE_KEY_USUARIOS)
            Usuario.invalidar_cache_supervisores_por_area()
            flash_t('user_created_success', 'success', nome=nome)
            return redirect(url_for('main.gerenciar_usuarios'))
        except Exception as e:
            logger.exception(f"Erro ao criar usuário: {str(e)}")
            flash_t('error_creating_user', 'danger', error=str(e))
            return redirect(url_for('main.gerenciar_usuarios'))
    try:
        usuarios = Usuario.get_all()
        return render_template('usuarios.html', usuarios=usuarios)
    except Exception as e:
        logger.exception(f"Erro ao listar usuários: {str(e)}")
        flash_t('error_loading_users', 'danger')
        return redirect(url_for('main.admin'))


@main.route('/admin/usuarios/novo', methods=['GET'])
@requer_perfil('admin')
def novo_usuario_form() -> Response:
    """Exibe formulário de criação de usuário."""
    return render_template('usuario_form.html', usuario=None)


@main.route('/admin/usuarios/<usuario_id>/editar', methods=['GET', 'POST'])
@requer_perfil('admin')
def editar_usuario(usuario_id: str) -> Response:
    """GET: exibe formulário de edição. POST: edita usuário."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t('user_not_found', 'danger')
            return redirect(url_for('main.gerenciar_usuarios'))
        if request.method == 'GET':
            return render_template('usuario_form.html', usuario=usuario)
        email = request.form.get('email', '').strip().lower()
        nome = request.form.get('nome', '').strip()
        perfil = request.form.get('perfil', usuario.perfil)
        areas = [a.strip() for a in request.form.getlist('areas') if a.strip()]
        erros = []
        if email and email != usuario.email:
            if '@' not in email:
                erros.append('invalid_email')
            elif Usuario.email_existe(email, usuario_id):
                erros.append('email_exists')
        if not nome or len(nome) < 3:
            erros.append('name_min_chars')
        if perfil not in ['solicitante', 'supervisor', 'admin']:
            erros.append('invalid_profile')
        if perfil == 'supervisor' and not areas:
            erros.append('area_required_for_supervisor')
        if erros:
            for e in erros:
                flash_t(e, 'danger')
            return redirect(url_for('main.gerenciar_usuarios'))
        update_data = {}
        if email and email != usuario.email:
            update_data['email'] = email
        if nome:
            update_data['nome'] = nome
        if perfil:
            update_data['perfil'] = perfil
        if set(areas) != set(usuario.areas):
            update_data['areas'] = areas
        if update_data:
            usuario.update(**update_data)
            cache_delete(CACHE_KEY_USUARIOS)
            cache_delete(f'usuario_{usuario_id}')
            Usuario.invalidar_cache_supervisores_por_area()
        flash_t('user_updated_success', 'success', nome=nome)
        return redirect(url_for('main.gerenciar_usuarios'))
    except Exception as e:
        logger.exception(f"Erro ao editar usuário: {str(e)}")
        flash_t('error_editing_user', 'danger', error=str(e))
        return redirect(url_for('main.gerenciar_usuarios'))


@main.route('/admin/usuarios/<usuario_id>/deletar', methods=['POST'])
@requer_perfil('admin')
def deletar_usuario(usuario_id: str) -> Response:
    """Deleta usuário (exceto admin@dtx.aero)."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t('user_not_found', 'danger')
            return redirect(url_for('main.gerenciar_usuarios'))
        if usuario_id == current_user.id:
            flash_t('cannot_delete_own_account', 'warning')
            return redirect(url_for('main.gerenciar_usuarios'))
        if usuario.email == 'admin@dtx.aero':
            flash_t('cannot_delete_root_admin', 'danger')
            logger.warning(
                "Tentativa de deletar admin@dtx.aero por %s",
                current_user.email,
            )
            return redirect(url_for('main.gerenciar_usuarios'))
        nome_usuario = usuario.nome
        usuario.delete()
        cache_delete(CACHE_KEY_USUARIOS)
        cache_delete(f'usuario_{usuario_id}')
        Usuario.invalidar_cache_supervisores_por_area()
        flash_t('user_deleted_success', 'success', nome=nome_usuario)
        return redirect(url_for('main.gerenciar_usuarios'))
    except Exception as e:
        logger.exception(f"Erro ao deletar usuário: {str(e)}")
        flash_t('error_deleting_user', 'danger', error=str(e))
        return redirect(url_for('main.gerenciar_usuarios'))

@main.route('/admin/usuarios/<usuario_id>/resetar-senha', methods=['POST'])
@requer_perfil('admin')
def resetar_senha_usuario(usuario_id: str) -> Response:
    """Reseta a senha de um usuário para a senha padrão (123456)."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t('user_not_found', 'danger')
            return redirect(url_for('main.gerenciar_usuarios'))

        if usuario_id == current_user.id:
            flash_t('cannot_reset_own_password', 'warning')
            return redirect(url_for('main.gerenciar_usuarios'))

        nome_usuario = usuario.nome
        usuario.set_password('123456')
        usuario.update(
            must_change_password=(usuario.perfil in ['solicitante', 'supervisor'])
        )

        cache_delete(CACHE_KEY_USUARIOS)
        cache_delete(f'usuario_{usuario_id}')

        logger.info(
            "Senha resetada para %s por %s",
            usuario.email,
            current_user.email,
        )
        flash_t('user_password_reset_success', 'success', nome=nome_usuario)
        return redirect(url_for('main.gerenciar_usuarios'))

    except Exception as e:
        logger.exception(f"Erro ao resetar senha do usuário: {str(e)}")
        flash_t('error_resetting_password', 'danger', error=str(e))
        return redirect(url_for('main.gerenciar_usuarios'))

@main.route('/admin/usuarios/<usuario_id>/reset-exp', methods=['POST'])
@requer_perfil('admin')
def resetar_exp_usuario(usuario_id: str) -> Response:
    """Zera a experiência e nível do usuário."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t('user_not_found', 'danger')
            return redirect(url_for('main.gerenciar_usuarios'))

        nome_usuario = usuario.nome
        usuario.update(gamification={
            'exp_total': 0,
            'exp_semanal': 0,
            'level': 1,
            'conquistas': []
        })

        cache_delete(CACHE_KEY_USUARIOS)
        cache_delete(f'usuario_{usuario_id}')
        Usuario.invalidar_cache_supervisores_por_area()

        # Opcional: deletar cache do ranking
        cache_delete('ranking_gamificacao_semanal')

        flash_t('user_exp_reset_success', 'success', nome=nome_usuario)
        return redirect(url_for('main.gerenciar_usuarios'))

    except Exception as e:
        logger.exception(f"Erro ao resetar EXP do usuário: {str(e)}")
        flash_t('error_resetting_exp', 'danger', error=str(e))
        return redirect(url_for('main.gerenciar_usuarios'))

