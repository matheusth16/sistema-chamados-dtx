"""Rotas de administração de categorias: setores, gates, impactos. Apenas para admins."""
import logging
from flask import render_template, request, redirect, url_for, flash, Response
from app.routes import main
from app.limiter import limiter
from app.decoradores import requer_perfil
from app.models_categorias import CategoriaSetor, CategoriaGate, CategoriaImpacto
from app.services.translation_service import adicionar_traducao_customizada

logger = logging.getLogger(__name__)


@main.route('/admin/categorias', methods=['GET'])
@requer_perfil('admin')
@limiter.limit("30 per minute")
def admin_categorias() -> Response:
    """Página de administração de categorias (setores, gates, impactos)."""
    try:
        setores = CategoriaSetor.get_all()
        gates = CategoriaGate.get_all()
        impactos = CategoriaImpacto.get_all()
        
        return render_template(
            'admin_categorias.html',
            setores=setores,
            gates=gates,
            impactos=impactos,
        )
    except Exception as e:
        logger.exception(f"Erro ao carregar categorias: {str(e)}")
        flash('Erro ao carregar categorias. Tente novamente.', 'danger')
        return redirect(url_for('main.admin'))


@main.route('/admin/categorias/setor/nova', methods=['POST'])
@requer_perfil('admin')
@limiter.limit("30 per minute")
def criar_setor() -> Response:
    """Cria um novo setor."""
    try:
        nome_pt = request.form.get('nome_pt', '').strip()
        descricao_pt = request.form.get('descricao_pt', '').strip()
        
        if not nome_pt:
            flash('Nome do setor é obrigatório', 'danger')
            return redirect(url_for('main.admin_categorias'))
        
        # Cria o setor (tradução automática)
        setor = CategoriaSetor(
            nome_pt=nome_pt,
            descricao_pt=descricao_pt,
        )
        setor.save()
        
        # Adiciona a tradução customizada para futuras referências
        adicionar_traducao_customizada(nome_pt, setor.nome_en, setor.nome_es)
        
        flash(f'Setor "{nome_pt}" criado com sucesso (traduzido automaticamente)', 'success')
        return redirect(url_for('main.admin_categorias'))
    except Exception as e:
        logger.exception(f"Erro ao criar setor: {str(e)}")
        flash(f'Erro ao criar setor: {str(e)}', 'danger')
        return redirect(url_for('main.admin_categorias'))


@main.route('/admin/categorias/gate/nova', methods=['POST'])
@requer_perfil('admin')
@limiter.limit("30 per minute")
def criar_gate() -> Response:
    """Cria um novo gate."""
    try:
        nome_pt = request.form.get('nome_pt', '').strip()
        descricao_pt = request.form.get('descricao_pt', '').strip()
        
        if not nome_pt:
            flash('Nome do gate é obrigatório', 'danger')
            return redirect(url_for('main.admin_categorias'))
        
        # Calcula próxima ordem: pega o maior valor existente + 1
        gates_existentes = CategoriaGate.get_all()
        if gates_existentes:
            proxima_ordem = max(g.ordem for g in gates_existentes) + 1
        else:
            proxima_ordem = 1
        
        # Cria o gate (tradução automática)
        gate = CategoriaGate(
            nome_pt=nome_pt,
            descricao_pt=descricao_pt,
            ordem=proxima_ordem,
        )
        gate.save()
        
        # Adiciona a tradução customizada
        adicionar_traducao_customizada(nome_pt, gate.nome_en, gate.nome_es)
        
        flash(f'Gate "{nome_pt}" criado com sucesso (ordem: {proxima_ordem}, traduzido automaticamente)', 'success')
        return redirect(url_for('main.admin_categorias'))
    except Exception as e:
        logger.exception(f"Erro ao criar gate: {str(e)}")
        flash(f'Erro ao criar gate: {str(e)}', 'danger')
        return redirect(url_for('main.admin_categorias'))


@main.route('/admin/categorias/impacto/nova', methods=['POST'])
@requer_perfil('admin')
@limiter.limit("30 per minute")
def criar_impacto() -> Response:
    """Cria um novo impacto."""
    try:
        nome_pt = request.form.get('nome_pt', '').strip()
        descricao_pt = request.form.get('descricao_pt', '').strip()
        
        if not nome_pt:
            flash('Nome do impacto é obrigatório', 'danger')
            return redirect(url_for('main.admin_categorias'))
        
        # Cria o impacto (tradução automática)
        impacto = CategoriaImpacto(
            nome_pt=nome_pt,
            descricao_pt=descricao_pt,
        )
        impacto.save()
        
        # Adiciona a tradução customizada
        adicionar_traducao_customizada(nome_pt, impacto.nome_en, impacto.nome_es)
        
        flash(f'Impacto "{nome_pt}" criado com sucesso (traduzido automaticamente)', 'success')
        return redirect(url_for('main.admin_categorias'))
    except Exception as e:
        logger.exception(f"Erro ao criar impacto: {str(e)}")
        flash(f'Erro ao criar impacto: {str(e)}', 'danger')
        return redirect(url_for('main.admin_categorias'))


@main.route('/admin/categorias/setor/<setor_id>/editar', methods=['POST'])
@requer_perfil('admin')
@limiter.limit("30 per minute")
def editar_setor(setor_id: str) -> Response:
    """Edita um setor existente."""
    try:
        setor = CategoriaSetor.get_by_id(setor_id)
        if not setor:
            flash('Setor não encontrado', 'danger')
            return redirect(url_for('main.admin_categorias'))
        
        setor.nome_pt = request.form.get('nome_pt', setor.nome_pt).strip()
        setor.descricao_pt = request.form.get('descricao_pt', setor.descricao_pt).strip()
        setor.ativo = request.form.get('ativo') == 'on'
        
        setor.save()
        flash(f'Setor "{setor.nome_pt}" atualizado com sucesso', 'success')
        return redirect(url_for('main.admin_categorias'))
    except Exception as e:
        logger.exception(f"Erro ao editar setor: {str(e)}")
        flash(f'Erro ao editar setor: {str(e)}', 'danger')
        return redirect(url_for('main.admin_categorias'))


@main.route('/admin/categorias/gate/<gate_id>/editar', methods=['POST'])
@requer_perfil('admin')
@limiter.limit("30 per minute")
def editar_gate(gate_id: str) -> Response:
    """Edita um gate existente."""
    try:
        gate = CategoriaGate.get_by_id(gate_id)
        if not gate:
            flash('Gate não encontrado', 'danger')
            return redirect(url_for('main.admin_categorias'))
        
        gate.nome_pt = request.form.get('nome_pt', gate.nome_pt).strip()
        gate.descricao_pt = request.form.get('descricao_pt', gate.descricao_pt).strip()
        gate.ativo = request.form.get('ativo') == 'on'
        
        gate.save()
        flash(f'Gate "{gate.nome_pt}" atualizado com sucesso', 'success')
        return redirect(url_for('main.admin_categorias'))
    except Exception as e:
        logger.exception(f"Erro ao editar gate: {str(e)}")
        flash(f'Erro ao editar gate: {str(e)}', 'danger')
        return redirect(url_for('main.admin_categorias'))


@main.route('/admin/categorias/impacto/<impacto_id>/editar', methods=['POST'])
@requer_perfil('admin')
@limiter.limit("30 per minute")
def editar_impacto(impacto_id: str) -> Response:
    """Edita um impacto existente."""
    try:
        impacto = CategoriaImpacto.get_by_id(impacto_id)
        if not impacto:
            flash('Impacto não encontrado', 'danger')
            return redirect(url_for('main.admin_categorias'))
        
        impacto.nome_pt = request.form.get('nome_pt', impacto.nome_pt).strip()
        impacto.descricao_pt = request.form.get('descricao_pt', impacto.descricao_pt).strip()
        impacto.ativo = request.form.get('ativo') == 'on'
        
        impacto.save()
        flash(f'Impacto "{impacto.nome_pt}" atualizado com sucesso', 'success')
        return redirect(url_for('main.admin_categorias'))
    except Exception as e:
        logger.exception(f"Erro ao editar impacto: {str(e)}")
        flash(f'Erro ao editar impacto: {str(e)}', 'danger')
        return redirect(url_for('main.admin_categorias'))
