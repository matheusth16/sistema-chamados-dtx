"""Rotas do painel administrativo: dashboard, exportar, histórico, usuários, relatórios, índices."""
import logging
import io
from datetime import datetime
from typing import List, Dict, Any
from flask import render_template, request, redirect, url_for, send_file, flash, Response
from flask_login import login_required, current_user
from firebase_admin import firestore
import pandas as pd
from config import Config
from app.routes import main
from app.limiter import limiter
from app.decoradores import requer_supervisor_area, requer_perfil
from app.database import db
from app.models import Chamado
from app.models_usuario import Usuario
from app.models_historico import Historico
from app.utils import formatar_data_para_excel, extrair_numero_chamado
from app.services.filters import aplicar_filtros_dashboard
from app.services.analytics import analisador
from app.services.notifications import notificar_solicitante_status
from app.services.pagination import OptimizadorQuery

logger = logging.getLogger(__name__)


@main.route('/admin', methods=['GET', 'POST'])
@requer_supervisor_area
@limiter.limit("30 per minute")
def admin() -> Response:
    """GET: dashboard com chamados. POST: alteração de status."""
    if request.method == 'POST':
        chamado_id = request.form.get('chamado_id')
        novo_status = request.form.get('novo_status')
        logger.debug(f"Alterar status: chamado_id={chamado_id}, novo_status={novo_status}")
        try:
            doc_anterior = db.collection('chamados').document(chamado_id).get()
            if not doc_anterior.exists:
                flash('Chamado não encontrado', 'danger')
                return redirect(url_for('main.admin', **request.args))
            data_anterior = doc_anterior.to_dict()
            status_anterior = data_anterior.get('status')
            if current_user.perfil == 'supervisor':
                if data_anterior.get('area') != current_user.area:
                    flash('Você só pode atualizar chamados da sua área', 'danger')
                    return redirect(url_for('main.admin', **request.args))
            update_data = {'status': novo_status}
            if novo_status == 'Concluído':
                update_data['data_conclusao'] = firestore.SERVER_TIMESTAMP
            db.collection('chamados').document(chamado_id).update(update_data)
            if status_anterior != novo_status:
                Historico(
                    chamado_id=chamado_id,
                    usuario_id=current_user.id,
                    usuario_nome=current_user.nome,
                    acao='alteracao_status',
                    campo_alterado='status',
                    valor_anterior=status_anterior,
                    valor_novo=novo_status
                ).save()
            if novo_status in ('Em Atendimento', 'Concluído'):
                try:
                    sid = data_anterior.get('solicitante_id')
                    sup = Usuario.get_by_id(sid) if sid else None
                    notificar_solicitante_status(
                        chamado_id=chamado_id,
                        numero_chamado=data_anterior.get('numero_chamado') or 'N/A',
                        novo_status=novo_status,
                        categoria=data_anterior.get('categoria') or 'Chamado',
                        solicitante_usuario=sup,
                    )
                except Exception as e:
                    logger.warning(f"Notificação ao solicitante não enviada: {e}")
            flash(f'Status alterado para {novo_status}', 'success')
            return redirect(url_for('main.admin', **request.args))
        except Exception as e:
            logger.exception(f"Erro ao atualizar chamado {chamado_id}: {str(e)}")
            flash(f'Erro ao atualizar: {str(e)}', 'danger')
            return redirect(url_for('main.admin', **request.args))

    # Lista de responsáveis (apenas supervisores; admin do sistema não aparece no filtro)
    usuarios_gestao = Usuario.get_all()
    lista_responsaveis = sorted(
        [u.nome for u in usuarios_gestao if u.perfil == 'supervisor' and u.nome],
        key=lambda x: x.upper()
    )

    chamados_ref = db.collection('chamados')
    docs = aplicar_filtros_dashboard(chamados_ref, request.args)
    chamados = []
    for doc in docs:
        data = doc.to_dict()
        c = Chamado.from_dict(data, doc.id)
        # Supervisor vê chamados da sua área OU chamados atribuídos a ele OU responsável está no seu setor
        if current_user.perfil == 'supervisor':
            # Busca area do responsavel para comparacao
            responsavel_obj = Usuario.get_by_id(c.responsavel_id) if c.responsavel_id else None
            responsavel_area = responsavel_obj.area if responsavel_obj else None
            
            # Mostrar se: (area == sua area) OR (você é responsável) OR (responsável é do seu setor)
            if not (c.area == current_user.area or c.responsavel_id == current_user.id or responsavel_area == current_user.area):
                continue
        chamados.append(c)

    def _chave(c):
        concluido = c.status == 'Concluído'
        num_id = extrair_numero_chamado(c.numero_chamado)
        if concluido:
            return (True, 0, num_id)
        prioridade_cat = 0 if c.categoria == 'Projetos' else 1
        return (False, prioridade_cat, num_id)
    chamados_ordenados = sorted(chamados, key=_chave)
    pagina = request.args.get('pagina', 1, type=int)
    itens_por_pagina = Config.ITENS_POR_PAGINA
    total_chamados = len(chamados_ordenados)
    inicio = (pagina - 1) * itens_por_pagina
    fim = inicio + itens_por_pagina
    total_paginas = (total_chamados + itens_por_pagina - 1) // itens_por_pagina
    if pagina < 1 or pagina > total_paginas:
        pagina = 1
        chamados_pagina = chamados_ordenados[:itens_por_pagina]
    else:
        chamados_pagina = chamados_ordenados[inicio:fim]
    return render_template(
        'dashboard.html',
        chamados=chamados_pagina,
        pagina_atual=pagina,
        total_paginas=total_paginas,
        total_chamados=total_chamados,
        itens_por_pagina=itens_por_pagina,
        lista_responsaveis=lista_responsaveis,
    )


@main.route('/chamado/<chamado_id>/historico')
@requer_supervisor_area
def visualizar_historico(chamado_id: str) -> Response:
    """Exibe histórico de alterações do chamado."""
    try:
        doc_chamado = db.collection('chamados').document(chamado_id).get()
        if not doc_chamado.exists:
            flash('Chamado não encontrado', 'danger')
            return redirect(url_for('main.admin'))
        chamado = Chamado.from_dict(doc_chamado.to_dict(), chamado_id)
        if current_user.perfil == 'supervisor':
            # Busca area do responsavel
            responsavel_obj = Usuario.get_by_id(chamado.responsavel_id) if chamado.responsavel_id else None
            responsavel_area = responsavel_obj.area if responsavel_obj else None
            
            # Permite acesso se: você está na mesma area do chamado OU é responsável OU responsável é do seu setor
            if not (chamado.area == current_user.area or chamado.responsavel_id == current_user.id or responsavel_area == current_user.area):
                flash('Você só pode visualizar histórico de chamados da sua área', 'danger')
                return redirect(url_for('main.admin'))
        historico = Historico.get_by_chamado_id(chamado_id)
        return render_template('historico.html', chamado=chamado, historico=historico)
    except Exception as e:
        logger.exception(f"Erro ao buscar histórico de {chamado_id}: {str(e)}")
        flash('Erro ao buscar histórico', 'danger')
        return redirect(url_for('main.admin'))


@main.route('/exportar')
@requer_supervisor_area
@limiter.limit("5 per hour")
def exportar() -> Response:
    """Exporta chamados filtrados para Excel."""
    try:
        chamados_ref = db.collection('chamados')
        docs = aplicar_filtros_dashboard(chamados_ref, request.args)
        dados: List[Dict[str, Any]] = []
        for doc in docs:
            c = Chamado.from_dict(doc.to_dict(), doc.id)
            if current_user.perfil == 'supervisor':
                # Mesma lógica de permissão do dashboard: área do chamado OU responsável do setor
                responsavel_obj = Usuario.get_by_id(c.responsavel_id) if c.responsavel_id else None
                responsavel_area = responsavel_obj.area if responsavel_obj else None
                
                if not (c.area == current_user.area or c.responsavel_id == current_user.id or responsavel_area == current_user.area):
                    continue
            dados.append({
                'Chamado': c.numero_chamado,
                'Categoria': c.categoria,
                'RL': c.rl_codigo or '-',
                'Tipo': c.tipo_solicitacao,
                'Gate': c.gate or '-',
                'Responsável': c.responsavel,
                'Solicitante': c.solicitante_nome or '-',
                'Área': c.area or '-',
                'Status': c.status,
                'Anexo': c.anexo or '-',
                'Abertura': formatar_data_para_excel(c.data_abertura),
                'Conclusão': formatar_data_para_excel(c.data_conclusao),
                'Descrição': c.descricao
            })
        df = pd.DataFrame(dados)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Chamados')
        output.seek(0)
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'relatorio_chamados_{ts}.xlsx'
        )
    except Exception as e:
        logger.exception(f"Erro ao exportar: {str(e)}")
        flash('Erro ao exportar dados. Tente novamente.', 'danger')
        return redirect(url_for('main.admin'))


@main.route('/admin/usuarios', methods=['GET', 'POST'])
@requer_perfil('admin')
@limiter.limit("30 per minute")
def gerenciar_usuarios() -> Response:
    """GET: lista usuários. POST: cria usuário."""
    if request.method == 'POST' and request.form.get('acao') == 'criar':
        email = request.form.get('email', '').strip().lower()
        nome = request.form.get('nome', '').strip()
        perfil = request.form.get('perfil', 'solicitante')
        area = request.form.get('area', '').strip() or None
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
        if perfil in ['supervisor', 'admin'] and not area:
            erros.append('Área é obrigatória para supervisores e admins')
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
                area=area
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


@main.route('/admin/usuarios/<usuario_id>/editar', methods=['POST'])
@requer_perfil('admin')
@limiter.limit("30 per minute")
def editar_usuario(usuario_id: str) -> Response:
    """Edita usuário."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash('Usuário não encontrado', 'danger')
            return redirect(url_for('main.gerenciar_usuarios'))
        email = request.form.get('email', '').strip().lower()
        nome = request.form.get('nome', '').strip()
        perfil = request.form.get('perfil', usuario.perfil)
        area = request.form.get('area', '').strip() or None
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
        if perfil in ['supervisor', 'admin'] and not area:
            erros.append('Área é obrigatória para supervisores e admins')
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
        if area != usuario.area:
            update_data['area'] = area
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


@main.route('/admin/indices-firestore')
@login_required
def indices_firestore() -> Response:
    """Página de documentação dos índices Firestore."""
    try:
        indices = OptimizadorQuery.INDICES_RECOMENDADOS
        script = OptimizadorQuery.gerar_script_indices()
        return render_template('indices_firestore.html', indices=indices, script=script)
    except Exception as e:
        logger.exception(f"Erro ao exibir índices: {str(e)}")
        flash('Erro ao carregar informações de índices', 'danger')
        return redirect(url_for('main.admin'))


@main.route('/exportar-avancado')
@requer_supervisor_area
@limiter.limit("3 per hour")
def exportar_avancado() -> Response:
    """Exporta relatório completo e profissional em Excel com múltiplas abas."""
    try:
        from app.services.excel_export_service import exportador_excel
        
        # Busca chamados com filtros
        chamados_ref = db.collection('chamados')
        docs = aplicar_filtros_dashboard(chamados_ref, request.args)
        chamados = []
        
        for doc in docs:
            c = Chamado.from_dict(doc.to_dict(), doc.id)
            if current_user.perfil == 'supervisor':
                # Mesma lógica de permissão: área do chamado OU responsável do setor
                responsavel_obj = Usuario.get_by_id(c.responsavel_id) if c.responsavel_id else None
                responsavel_area = responsavel_obj.area if responsavel_obj else None
                
                if not (c.area == current_user.area or c.responsavel_id == current_user.id or responsavel_area == current_user.area):
                    continue
            chamados.append(c)
        
        # Obtém métricas
        analisador_local = analisador
        metricas_gerais = analisador_local.obter_metricas_gerais(dias=30)
        metricas_supervisores = analisador_local.obter_metricas_supervisores()
        
        # Filtros aplicados (para documenti no Excel)
        filtros_aplicados = {}
        if request.args.get('search'):
            filtros_aplicados['Busca'] = request.args.get('search')
        if request.args.get('categoria'):
            filtros_aplicados['Categoria'] = request.args.get('categoria')
        if request.args.get('status'):
            filtros_aplicados['Status'] = request.args.get('status')
        if request.args.get('responsavel'):
            filtros_aplicados['Responsável'] = request.args.get('responsavel')
        
        # Exporta relatório
        output = exportador_excel.exportar_relatorio_completo(
            chamados=chamados,
            metricas_gerais=metricas_gerais,
            metricas_supervisores=metricas_supervisores,
            filtros_aplicados=filtros_aplicados
        )
        
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'relatorio_completo_{ts}.xlsx'
        )
    except Exception as e:
        logger.exception(f"Erro ao exportar relatório avançado: {str(e)}")
        flash('Erro ao exportar relatório. Tente novamente.', 'danger')
        return redirect(url_for('main.admin'))


@main.route('/admin/relatorios')
@requer_supervisor_area
@limiter.limit("30 per minute")
def relatorios() -> Response:
    """Dashboard de relatórios e análises. Use ?atualizar=1 para forçar dados frescos."""
    try:
        atualizar = request.args.get('atualizar') == '1'
        relatorio = analisador.obter_relatorio_completo(usar_cache=not atualizar)
        return render_template(
            'relatorios.html',
            relatorio=relatorio,
            metricas_gerais=relatorio.get('metricas_gerais', {}),
            metricas_supervisores=relatorio.get('metricas_supervisores', []),
            metricas_areas=relatorio.get('metricas_areas', []),
            analise_atribuicao=relatorio.get('analise_atribuicao', {}),
            insights=relatorio.get('insights', [])
        )
    except Exception as e:
        logger.exception(f"Erro ao gerar relatórios: {str(e)}")
        flash('Erro ao gerar relatórios. Tente novamente.', 'danger')
        return redirect(url_for('main.admin'))
