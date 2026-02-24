"""Rotas de gerenciamento de usuários (CRUD). Apenas para admins."""
import logging
from flask import render_template, request, redirect, url_for, flash, Response
from flask_login import current_user
from app.routes import main
from app.limiter import limiter
from app.decoradores import requer_perfil
from app.models_usuario import Usuario

logger = logging.getLogger(__name__)


@main.route('/admin/usuarios', methods=['GET', 'POST'])
@requer_perfil('admin')
@limiter.limit("30 per minute")
def gerenciar_usuarios() -> Response:
    """GET: lista usuários. POST: cria usuário."""
    if request.method == 'POST' and request.form.get('acao') == 'criar':
        email = request.form.get('email', '').strip().lower()
        nome = request.form.get('nome', '').strip()
        perfil = request.form.get('perfil', 'solicitante')
        areas = [a.strip() for a in request.form.getlist('areas') if a.strip()]
        senha = request.form.get('senha', '')
        erros = []
        if not email or '@' not in email:
            erros.append('Email inválido')
        elif Usuario.email_existe(email):
            erros.append('Email já existe no sistema')
        if not nome or len(nome) < 3:
            erros.append('Nome deve ter pelo menos 3 caracteres')
        if perfil not in ['solicitante', 'supervisor', 'admin']:
            erros.append('Perfil inválido')
        if perfil in ['supervisor', 'admin'] and not areas:
            erros.append('Pelo menos uma Área é obrigatória para supervisores e admins')
        if not senha or len(senha) < 6:
            erros.append('Senha deve ter pelo menos 6 caracteres')
        if erros:
            for e in erros:
                flash(e, 'danger')
            return redirect(url_for('main.gerenciar_usuarios'))
        try:
            u = Usuario(
                id=f"user_{email.split('@')[0]}_{hash(email) % 100000}",
                email=email,
                nome=nome,
                perfil=perfil,
                areas=areas
            )
            u.set_password(senha)
            u.save()
            flash(f'Usuário {nome} criado com sucesso!', 'success')
            return redirect(url_for('main.gerenciar_usuarios'))
        except Exception as e:
            logger.exception(f"Erro ao criar usuário: {str(e)}")
            flash(f'Erro ao criar usuário: {str(e)}', 'danger')
            return redirect(url_for('main.gerenciar_usuarios'))
    try:
        usuarios = Usuario.get_all()
        return render_template('usuarios.html', usuarios=usuarios)
    except Exception as e:
        logger.exception(f"Erro ao listar usuários: {str(e)}")
        flash('Erro ao carregar usuários', 'danger')
        return redirect(url_for('main.admin'))


@main.route('/admin/usuarios/novo', methods=['GET'])
@requer_perfil('admin')
@limiter.limit("30 per minute")
def novo_usuario_form() -> Response:
    """Exibe formulário de criação de usuário."""
    return render_template('usuario_form.html', usuario=None)


@main.route('/admin/usuarios/<usuario_id>/editar', methods=['GET', 'POST'])
@requer_perfil('admin')
@limiter.limit("30 per minute")
def editar_usuario(usuario_id: str) -> Response:
    """GET: exibe formulário de edição. POST: edita usuário."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash('Usuário não encontrado', 'danger')
            return redirect(url_for('main.gerenciar_usuarios'))
        if request.method == 'GET':
            return render_template('usuario_form.html', usuario=usuario)
        email = request.form.get('email', '').strip().lower()
        nome = request.form.get('nome', '').strip()
        perfil = request.form.get('perfil', usuario.perfil)
        areas = [a.strip() for a in request.form.getlist('areas') if a.strip()]
        senha = request.form.get('senha', '').strip()
        erros = []
        if email and email != usuario.email:
            if '@' not in email:
                erros.append('Email inválido')
            elif Usuario.email_existe(email, usuario_id):
                erros.append('Email já existe no sistema')
        if not nome or len(nome) < 3:
            erros.append('Nome deve ter pelo menos 3 caracteres')
        if perfil not in ['solicitante', 'supervisor', 'admin']:
            erros.append('Perfil inválido')
        if perfil in ['supervisor', 'admin'] and not areas:
            erros.append('Pelo menos uma Área é obrigatória para supervisores e admins')
        if senha and len(senha) < 6:
            erros.append('Senha deve ter pelo menos 6 caracteres')
        if erros:
            for e in erros:
                flash(e, 'danger')
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
        if senha:
            update_data['senha'] = senha
        if update_data:
            usuario.update(**update_data)
        flash(f'Usuário {nome} atualizado com sucesso!', 'success')
        return redirect(url_for('main.gerenciar_usuarios'))
    except Exception as e:
        logger.exception(f"Erro ao editar usuário: {str(e)}")
        flash(f'Erro ao editar usuário: {str(e)}', 'danger')
        return redirect(url_for('main.gerenciar_usuarios'))


@main.route('/admin/usuarios/<usuario_id>/deletar', methods=['POST'])
@requer_perfil('admin')
@limiter.limit("30 per minute")
def deletar_usuario(usuario_id: str) -> Response:
    """Deleta usuário."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash('Usuário não encontrado', 'danger')
            return redirect(url_for('main.gerenciar_usuarios'))
        if usuario_id == current_user.id:
            flash('Você não pode deletar sua própria conta!', 'warning')
            return redirect(url_for('main.gerenciar_usuarios'))
        nome_usuario = usuario.nome
        usuario.delete()
        flash(f'Usuário {nome_usuario} foi removido do sistema', 'success')
        return redirect(url_for('main.gerenciar_usuarios'))
    except Exception as e:
        logger.exception(f"Erro ao deletar usuário: {str(e)}")
        flash(f'Erro ao deletar usuário: {str(e)}', 'danger')
        return redirect(url_for('main.gerenciar_usuarios'))
