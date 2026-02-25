"""Rotas do painel administrativo: dashboard, exportar, histórico, relatórios, índices."""
import logging
import io
from datetime import datetime
from typing import List, Dict, Any
from flask import render_template, request, redirect, url_for, send_file, flash, Response
from app.i18n import flash_t
from flask_login import login_required, current_user
from firebase_admin import firestore
import pandas as pd
from config import Config
from app.routes import main
from app.limiter import limiter
from app.decoradores import requer_supervisor_area
from app.database import db
from app.models import Chamado
from app.models_usuario import Usuario
from app.models_historico import Historico
from app.utils import formatar_data_para_excel, extrair_numero_chamado
from app.services.filters import aplicar_filtros_dashboard, aplicar_filtros_dashboard_com_paginacao
from app.services.excel_export_service import MAX_EXPORT_CHAMADOS
from app.services.analytics import analisador, obter_sla_para_exibicao
from app.services.pagination import OptimizadorQuery
from app.services.status_service import atualizar_status_chamado
from app.services.permissions import usuario_pode_ver_chamado, usuario_pode_ver_chamado_otimizado
from app.models_categorias import CategoriaGate

logger = logging.getLogger(__name__)


def _filtrar_chamados_por_permissao(docs, user) -> list:
    """Filtra chamados que o usuário pode ver, com cache para evitar N+1 queries."""
    chamados = []
    
    if user.perfil == 'admin':
        # Admin vê tudo, sem checagem extra
        for doc in docs:
            chamados.append(Chamado.from_dict(doc.to_dict(), doc.id))
        return chamados
    
    # Supervisor: usar versão otimizada com cache de usuários
    # Primeiro, coletamos todos os chamados e responsável IDs
    chamados_raw = []
    responsavel_ids = set()
    for doc in docs:
        c = Chamado.from_dict(doc.to_dict(), doc.id)
        chamados_raw.append(c)
        if c.responsavel_id:
            responsavel_ids.add(c.responsavel_id)
    
    # Pré-carrega todos os responsáveis de uma vez (evita N+1)
    cache_usuarios = {}
    for uid in responsavel_ids:
        u = Usuario.get_by_id(uid)
        if u:
            cache_usuarios[uid] = u
    
    # Filtra usando a versão otimizada
    for c in chamados_raw:
        if usuario_pode_ver_chamado_otimizado(user, c, cache_usuarios):
            chamados.append(c)
    
    return chamados


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
            # Verificação de permissão para supervisores
            if current_user.perfil == 'supervisor':
                doc_anterior = db.collection('chamados').document(chamado_id).get()
                if not doc_anterior.exists:
                    flash_t('ticket_not_found', 'danger')
                    return redirect(url_for('main.admin', **request.args))
                data_anterior = doc_anterior.to_dict()
                if data_anterior.get('area') not in current_user.areas:
                    flash_t('only_update_tickets_your_area', 'danger')
                    return redirect(url_for('main.admin', **request.args))

            # Delega ao serviço centralizado de status
            resultado = atualizar_status_chamado(
                chamado_id=chamado_id,
                novo_status=novo_status,
                usuario_id=current_user.id,
                usuario_nome=current_user.nome,
            )
            if resultado['sucesso']:
                flash(resultado['mensagem'], 'success')
            else:
                if 'erro' in resultado:
                    flash(resultado['erro'], 'danger')
                else:
                    flash_t('error_updating', 'danger')
            return redirect(url_for('main.admin', **request.args))
        except Exception as e:
            logger.exception(f"Erro ao atualizar chamado {chamado_id}: {str(e)}")
            flash_t('error_updating_with_msg', 'danger', error=str(e))
            return redirect(url_for('main.admin', **request.args))

    # Lista de responsáveis (apenas supervisores; admin do sistema não aparece no filtro)
    usuarios_gestao = Usuario.get_all()
    lista_responsaveis = sorted(
        [u.nome for u in usuarios_gestao if u.perfil == 'supervisor' and u.nome],
        key=lambda x: x.upper()
    )
    
    # Para o formulário de edição do modal: lista com ID, Nome e Área
    supervisores_detalhados = sorted(
        [{'id': u.id, 'nome': u.nome, 'area': u.area} for u in usuarios_gestao if u.perfil in ('supervisor', 'admin') and u.nome],
        key=lambda x: x['nome'].upper()
    )

    chamados_ref = db.collection('chamados')
    docs = aplicar_filtros_dashboard(chamados_ref, request.args)
    chamados = _filtrar_chamados_por_permissao(docs, current_user)

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
    # SLA por chamado para exibição na Gestão (sem query extra)
    for c in chamados_pagina:
        c.sla_info = obter_sla_para_exibicao(c)
    # Gates disponíveis (para dropdown dinâmico)
    lista_gates = sorted([g.nome_pt for g in CategoriaGate.get_all()])
    
    return render_template(
        'dashboard.html',
        chamados=chamados_pagina,
        pagina_atual=pagina,
        total_paginas=total_paginas,
        total_chamados=total_chamados,
        itens_por_pagina=itens_por_pagina,
        lista_responsaveis=lista_responsaveis,
        supervisores_detalhados=supervisores_detalhados,
        lista_gates=lista_gates,
        max=max,
        min=min,
    )


@main.route('/chamado/<chamado_id>/historico')
@requer_supervisor_area
def visualizar_historico(chamado_id: str) -> Response:
    """Exibe histórico de alterações do chamado."""
    try:
        doc_chamado = db.collection('chamados').document(chamado_id).get()
        if not doc_chamado.exists:
            flash_t('ticket_not_found', 'danger')
            return redirect(url_for('main.admin'))
        chamado = Chamado.from_dict(doc_chamado.to_dict(), chamado_id)
        if not usuario_pode_ver_chamado(current_user, chamado):
            flash_t('only_view_history_your_area', 'danger')
            return redirect(url_for('main.admin'))
        historico = Historico.get_by_chamado_id(chamado_id)
        return render_template('historico.html', chamado=chamado, historico=historico)
    except Exception as e:
        logger.exception(f"Erro ao buscar histórico de {chamado_id}: {str(e)}")
        flash_t('error_loading_history', 'danger')
        return redirect(url_for('main.admin'))


@main.route('/exportar')
@requer_supervisor_area
@limiter.limit("3 per hour")  # Evita abuso; cada exportação gera muitas leituras no Firestore
def exportar() -> Response:
    """Exporta chamados filtrados para Excel (até MAX_EXPORT_CHAMADOS)."""
    try:
        chamados_ref = db.collection('chamados')
        resultado = aplicar_filtros_dashboard_com_paginacao(
            chamados_ref, request.args, limite=MAX_EXPORT_CHAMADOS, cursor=None
        )
        docs = resultado['docs']
        chamados = _filtrar_chamados_por_permissao(docs, current_user)

        dados: List[Dict[str, Any]] = []
        for c in chamados:
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
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'relatorio_chamados_{ts}.xlsx'
        )
    except Exception as e:
        logger.exception(f"Erro ao exportar: {str(e)}")
        flash_t('error_exporting_data', 'danger')
        return redirect(url_for('main.admin'))


@main.route('/exportar-avancado')
@requer_supervisor_area
@limiter.limit("3 per hour")  # Evita abuso; cada exportação gera muitas leituras no Firestore
def exportar_avancado() -> Response:
    """Exporta relatório completo em Excel com múltiplas abas (até MAX_EXPORT_CHAMADOS)."""
    try:
        from app.services.excel_export_service import exportador_excel
        
        # Busca chamados com filtros e permissão (limitado para não estourar cota Firestore)
        chamados_ref = db.collection('chamados')
        resultado = aplicar_filtros_dashboard_com_paginacao(
            chamados_ref, request.args, limite=MAX_EXPORT_CHAMADOS, cursor=None
        )
        docs = resultado['docs']
        chamados = _filtrar_chamados_por_permissao(docs, current_user)
        
        # Obtém métricas
        metricas_gerais = analisador.obter_metricas_gerais(dias=30)
        metricas_supervisores = analisador.obter_metricas_supervisores()
        
        # Filtros aplicados (para documentar no Excel)
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
        flash_t('error_exporting_report', 'danger')
        return redirect(url_for('main.admin'))


@main.route('/admin/relatorios')
@requer_supervisor_area
@limiter.limit("30 per minute")
def relatorios() -> Response:
    """Dashboard de relatórios e análises. Use ?atualizar=1 para forçar dados frescos."""
    try:
        atualizar = request.args.get('atualizar') == '1'
        relatorio = analisador.obter_relatorio_completo(usar_cache=not atualizar)
        insights = relatorio.get('insights', [])
        # Ordenar por prioridade: aviso primeiro, depois sucesso, depois info
        ordem_tipo = {'aviso': 0, 'sucesso': 1, 'info': 2}
        insights = sorted(insights, key=lambda x: ordem_tipo.get(x.get('tipo'), 3))
        return render_template(
            'relatorios.html',
            relatorio=relatorio,
            metricas_gerais=relatorio.get('metricas_gerais', {}),
            metricas_supervisores=relatorio.get('metricas_supervisores', []),
            metricas_areas=relatorio.get('metricas_areas', []),
            insights=insights
        )
    except Exception as e:
        logger.exception(f"Erro ao gerar relatórios: {str(e)}")
        flash_t('error_generating_reports', 'danger')
        return redirect(url_for('main.admin'))


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
        flash_t('error_loading_index_info', 'danger')
        return redirect(url_for('main.admin'))
