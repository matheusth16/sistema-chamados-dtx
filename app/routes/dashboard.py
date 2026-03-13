"""Rotas do painel administrativo: dashboard, exportar, histórico, relatórios, índices."""
import logging
import io
from datetime import datetime
from typing import List, Dict, Any
from flask import render_template, request, redirect, url_for, send_file, flash, Response, current_app, session
from urllib.parse import urlparse
from app.i18n import flash_t, get_translation
from flask_login import login_required, current_user
from firebase_admin import firestore
from config import Config
from app.routes import main
from app.limiter import limiter
from app.decoradores import requer_perfil, requer_supervisor_area
from app.database import db
from app.models import Chamado
from app.models_usuario import Usuario
from app.models_historico import Historico
from app.utils import formatar_data_para_excel, extrair_numero_chamado
from app.services.filters import aplicar_filtros_dashboard, aplicar_filtros_dashboard_com_paginacao
from app.services.dashboard_service import obter_contexto_admin, _filtrar_chamados_por_permissao
from app.services.contadores_uso import verificar_e_incrementar_relatorio, verificar_e_incrementar_export
from app.services.excel_export_service import MAX_EXPORT_CHAMADOS
from app.services.analytics import analisador, obter_sla_para_exibicao
from app.services.pagination import OptimizadorQuery
from app.services.status_service import atualizar_status_chamado
from app.services.permissions import usuario_pode_ver_chamado, usuario_pode_ver_chamado_otimizado
from app.services.upload import salvar_anexo
from app.firebase_retry import execute_with_retry
from app.models_categorias import CategoriaGate, CategoriaSetor
from google.api_core.exceptions import FailedPrecondition
from app.services.notifications import notificar_setores_adicionais_chamado

logger = logging.getLogger(__name__)


def _same_origin(referrer: str) -> bool:
    """Retorna True se referrer tem a mesma origem (host) que a requisição atual."""
    if not referrer:
        return False
    try:
        ref = urlparse(referrer)
        base = urlparse(request.url_root)
        return ref.netloc == base.netloc and ref.scheme == base.scheme
    except Exception:
        return False


@main.route('/admin', methods=['GET', 'POST'])
@requer_supervisor_area
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

    itens_por_pagina = Config.ITENS_POR_PAGINA_DASHBOARD
    try:
        contexto = obter_contexto_admin(current_user, request.args, itens_por_pagina=itens_por_pagina)
        return render_template('dashboard.html', **contexto)
    except FailedPrecondition as e:
        msg = str(e).lower()
        if 'currently building' in msg or 'cannot be used yet' in msg:
            logger.warning("Índice Firestore em construção: %s", e)
            return render_template('dashboard_indice_construindo.html'), 503
        raise


@main.route('/chamado/<chamado_id>')
@login_required
def visualizar_detalhe_chamado(chamado_id: str) -> Response:
    """Exibe detalhes do chamado. Solicitante vê só os próprios; supervisor/admin conforme permissão."""
    try:
        doc_chamado = db.collection('chamados').document(chamado_id).get()
        if not doc_chamado.exists:
            flash_t('ticket_not_found', 'danger')
            return redirect(url_for('main.admin' if current_user.perfil in ('supervisor', 'admin') else 'main.meus_chamados'))
        chamado = Chamado.from_dict(doc_chamado.to_dict(), chamado_id)
        if current_user.perfil == 'solicitante':
            if chamado.solicitante_id != current_user.id:
                flash_t('ticket_not_found', 'danger')
                return redirect(url_for('main.meus_chamados'))
        else:
            if not usuario_pode_ver_chamado(current_user, chamado):
                flash_t('only_view_history_your_area', 'danger')
                return redirect(url_for('main.admin'))
        voltar_url = request.referrer if request.referrer and _same_origin(request.referrer) else (
            url_for('main.admin') if current_user.perfil in ('supervisor', 'admin') else url_for('main.meus_chamados')
        )
        pode_editar = current_user.perfil in ('supervisor', 'admin')
        usuarios_gestao = Usuario.get_all()
        supervisores_list = [u for u in usuarios_gestao if u.perfil == 'supervisor' and u.nome]
        if pode_editar and current_user.perfil == 'supervisor' and getattr(current_user, 'areas', None):
            user_areas_set = set(current_user.areas)
            supervisores_list = [u for u in supervisores_list if user_areas_set & set(getattr(u, 'areas', []))]
        supervisores_detalhados = sorted(
            [{'id': u.id, 'nome': u.nome, 'area': u.area} for u in supervisores_list],
            key=lambda x: (x['nome'] or '').upper()
        ) if pode_editar else []
        setores = [s for s in CategoriaSetor.get_all() if getattr(s, 'ativo', True)]
        return render_template(
            'visualizar_chamado.html',
            chamado=chamado,
            voltar_url=voltar_url,
            pode_editar=pode_editar,
            supervisores_detalhados=supervisores_detalhados,
            setores=setores
        )
    except Exception as e:
        logger.exception("Erro ao exibir chamado %s: %s", chamado_id, e)
        flash_t('ticket_not_found', 'danger')
        return redirect(url_for('main.admin' if current_user.perfil in ('supervisor', 'admin') else 'main.meus_chamados'))


@main.route('/chamado/editar', methods=['POST'])
@login_required
def editar_chamado_pagina() -> Response:
    """Processa o formulário de edição da página de detalhes do chamado (status, responsável, descrição, anexo)."""
    if current_user.perfil not in ('supervisor', 'admin'):
        flash_t('only_supervisor_can_edit', 'danger')
        return redirect(url_for('main.index'))

    chamado_id = request.form.get('chamado_id')
    if not chamado_id:
        flash_t('ticket_not_found', 'danger')
        return redirect(url_for('main.admin'))

    doc_chamado = db.collection('chamados').document(chamado_id).get()
    if not doc_chamado.exists:
        flash_t('ticket_not_found', 'danger')
        return redirect(url_for('main.admin'))

    chamado = Chamado.from_dict(doc_chamado.to_dict(), chamado_id)
    if not usuario_pode_ver_chamado(current_user, chamado):
        flash_t('only_view_history_your_area', 'danger')
        return redirect(url_for('main.admin'))

    from app.services.edicao_chamado_service import processar_edicao_chamado
    
    setores_adicionais_form = request.form.getlist('setores_adicionais')
    
    resultado = processar_edicao_chamado(
        usuario_atual=current_user,
        chamado_id=chamado_id,
        novo_status=request.form.get('novo_status'),
        motivo_cancelamento=(request.form.get('motivo_cancelamento') or '').strip(),
        nova_descricao=request.form.get('nova_descricao', ''),
        novo_responsavel_id=(request.form.get('novo_responsavel_id') or '').strip(),
        novo_sla_str=(request.form.get('sla_dias') or '').strip(),
        arquivo_anexo=request.files.get('anexo'),
        setores_adicionais_lista=setores_adicionais_form
    )
    
    if resultado.get('sucesso'):
        lang = session.get('language', 'en')
        mensagem = resultado.get('mensagem') or get_translation('changes_saved', lang)
        flash(mensagem, 'success')
    else:
        erro = resultado.get('erro', '')
        if erro:
            flash(erro, 'danger')
        else:
            flash_t('error_server', 'danger')

    return redirect(url_for('main.visualizar_detalhe_chamado', chamado_id=chamado_id))


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
def exportar() -> Response:
    """Exporta chamados filtrados para Excel (até MAX_EXPORT_CHAMADOS)."""
    limite_export = getattr(Config, 'EXPORT_EXCEL_MAX_POR_USUARIO_POR_DIA', 0) or 0
    if limite_export > 0:
        pode, msg = verificar_e_incrementar_export(current_user.id, limite_export)
        if not pode:
            if msg:
                flash(msg, 'warning')
            flash_t('error_exporting_data', 'danger')
            return redirect(url_for('main.admin'))
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
        import pandas as pd  # lazy: evita carregar numpy/pyarrow na inicialização
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
def exportar_avancado() -> Response:
    """Exporta relatório completo em Excel com múltiplas abas (até MAX_EXPORT_CHAMADOS)."""
    limite_export = getattr(Config, 'EXPORT_EXCEL_MAX_POR_USUARIO_POR_DIA', 0) or 0
    if limite_export > 0:
        pode, msg = verificar_e_incrementar_export(current_user.id, limite_export)
        if not pode:
            if msg:
                flash(msg, 'warning')
            flash_t('error_exporting_report', 'danger')
            return redirect(url_for('main.admin'))
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


def _relatorios_ordenar_supervisores(lista: List[Dict], campo: str, asc: bool) -> List[Dict]:
    """Ordena lista de métricas de supervisores por campo (total_chamados, carga_atual, taxa_resolucao_percentual, tempo_medio_resolucao_horas, supervisor_nome, area)."""
    reverse = not asc
    if campo == 'total':
        return sorted(lista, key=lambda x: x.get('total_chamados', 0), reverse=reverse)
    if campo == 'carga':
        return sorted(lista, key=lambda x: x.get('carga_atual', 0), reverse=reverse)
    if campo == 'taxa':
        return sorted(lista, key=lambda x: x.get('taxa_resolucao_percentual', 0), reverse=reverse)
    if campo == 'tempo':
        return sorted(lista, key=lambda x: x.get('tempo_medio_resolucao_horas', 0), reverse=reverse)
    if campo == 'nome':
        return sorted(lista, key=lambda x: (x.get('supervisor_nome') or '').lower(), reverse=reverse)
    if campo == 'area':
        return sorted(lista, key=lambda x: (x.get('area') or '').lower(), reverse=reverse)
    if campo == 'sla':
        def _sla_key(x):
            v = x.get('percentual_dentro_sla')
            return (v is None, -(v or 0))
        return sorted(lista, key=_sla_key, reverse=reverse)
    return lista


def _relatorios_ordenar_areas(lista: List[Dict], campo: str, asc: bool) -> List[Dict]:
    """Ordena lista de métricas por área (total_chamados, abertos, taxa_resolucao_percentual, tempo_medio_resolucao_horas, area)."""
    reverse = not asc
    if campo == 'total':
        return sorted(lista, key=lambda x: x.get('total_chamados', 0), reverse=reverse)
    if campo == 'abertos':
        return sorted(lista, key=lambda x: x.get('abertos', 0), reverse=reverse)
    if campo == 'taxa':
        return sorted(lista, key=lambda x: x.get('taxa_resolucao_percentual', 0), reverse=reverse)
    if campo == 'tempo':
        return sorted(lista, key=lambda x: x.get('tempo_medio_resolucao_horas', 0), reverse=reverse)
    if campo == 'area':
        return sorted(lista, key=lambda x: (x.get('area') or '').lower(), reverse=reverse)
    return lista


@main.route('/admin/relatorios')
@requer_supervisor_area
def relatorios() -> Response:
    """Dashboard de relatórios e análises. Use ?atualizar=1 para forçar dados frescos.
    Query params: pagina_sup, pagina_area, ordenar_sup, ordenar_area, ordem_sup, ordem_area (asc|desc), busca_sup, busca_area."""
    erro_relatorio = False
    try:
        atualizar = request.args.get('atualizar') == '1'
        if atualizar:
            limite = getattr(Config, 'RELATORIO_MAX_POR_USUARIO_POR_DIA', 0) or 0
            if limite > 0:
                pode, msg = verificar_e_incrementar_relatorio(current_user.id, limite)
                if not pode:
                    flash_t('generic_error', 'danger')
                    if msg:
                        flash(msg, 'warning')
                    return redirect(url_for('main.relatorios'))
        try:
            relatorio = analisador.obter_relatorio_completo(usar_cache=not atualizar) or {}
        except Exception as e_analytics:
            logger.exception("Erro ao obter relatório completo (analytics): %s", e_analytics)
            relatorio = {
                'data_geracao': None,
                'metricas_gerais': {},
                'metricas_supervisores': [],
                'metricas_areas': [],
                'insights': [],
            }
            erro_relatorio = True
        insights = list(relatorio.get('insights') or [])
        ordem_tipo = {'aviso': 0, 'sucesso': 1, 'info': 2}
        insights = sorted(insights, key=lambda x: ordem_tipo.get((x or {}).get('tipo'), 3))

        itens_por_pagina = max(1, int(getattr(Config, 'ITENS_POR_PAGINA', 10)))

        # Supervisores: lista completa para gráficos e para filtrar/ordenar/paginar
        metricas_supervisores_full = list(relatorio.get('metricas_supervisores') or [])
        busca_sup = (request.args.get('busca_sup') or '').strip().lower()
        if busca_sup:
            metricas_supervisores_full = [
                s for s in metricas_supervisores_full
                if busca_sup in (s.get('supervisor_nome') or '').lower()
                or busca_sup in (s.get('supervisor_email') or '').lower()
                or busca_sup in (s.get('area') or '').lower()
            ]
        ordenar_sup = request.args.get('ordenar_sup') or 'carga'
        ordem_sup = (request.args.get('ordem_sup') or 'desc').lower()
        if ordem_sup not in ('asc', 'desc'):
            ordem_sup = 'desc'
        metricas_supervisores_full = _relatorios_ordenar_supervisores(
            metricas_supervisores_full, ordenar_sup, ordem_sup == 'asc'
        )
        total_supervisores = len(metricas_supervisores_full)
        total_paginas_sup = max(1, (total_supervisores + itens_por_pagina - 1) // itens_por_pagina)
        pagina_sup = request.args.get('pagina_sup', 1, type=int)
        if pagina_sup < 1:
            pagina_sup = 1
        if pagina_sup > total_paginas_sup:
            pagina_sup = total_paginas_sup
        inicio_sup = (pagina_sup - 1) * itens_por_pagina
        metricas_supervisores = metricas_supervisores_full[inicio_sup : inicio_sup + itens_por_pagina]

        # Áreas: lista completa para gráficos e para filtrar/ordenar/paginar
        metricas_areas_full = list(relatorio.get('metricas_areas') or [])
        busca_area = (request.args.get('busca_area') or '').strip().lower()
        if busca_area:
            metricas_areas_full = [
                a for a in metricas_areas_full
                if busca_area in (a.get('area') or '').lower()
            ]
        ordenar_area = request.args.get('ordenar_area') or 'total'
        ordem_area = (request.args.get('ordem_area') or 'desc').lower()
        if ordem_area not in ('asc', 'desc'):
            ordem_area = 'desc'
        metricas_areas_full = _relatorios_ordenar_areas(
            metricas_areas_full, ordenar_area, ordem_area == 'asc'
        )
        total_areas = len(metricas_areas_full)
        total_paginas_area = max(1, (total_areas + itens_por_pagina - 1) // itens_por_pagina)
        pagina_area = request.args.get('pagina_area', 1, type=int)
        if pagina_area < 1:
            pagina_area = 1
        if pagina_area > total_paginas_area:
            pagina_area = total_paginas_area
        inicio_area = (pagina_area - 1) * itens_por_pagina
        metricas_areas = metricas_areas_full[inicio_area : inicio_area + itens_por_pagina]

        # Ranking Gamificação Top 3 da Semana
        # Aproveitar os usuários puxados do banco ou base no relatorio
        usuarios_gestao = Usuario.get_all()
        ranking_gamificacao = sorted(
            [u for u in usuarios_gestao if u.exp_semanal > 0 and u.perfil in ('supervisor', 'admin') and u.nome],
            key=lambda u: u.exp_semanal, 
            reverse=True
        )[:3]

        return render_template(
            'relatorios.html',
            relatorio=relatorio,
            ranking_gamificacao=ranking_gamificacao,
            metricas_gerais=relatorio.get('metricas_gerais') or {},
            metricas_supervisores=metricas_supervisores,
            metricas_supervisores_full=metricas_supervisores_full,
            metricas_areas=metricas_areas,
            metricas_areas_full=metricas_areas_full,
            insights=insights,
            data_geracao=relatorio.get('data_geracao'),
            pagina_sup=pagina_sup,
            total_paginas_sup=total_paginas_sup,
            total_supervisores=total_supervisores,
            itens_por_pagina_sup=itens_por_pagina,
            ordenar_sup=ordenar_sup,
            ordem_sup=ordem_sup,
            busca_sup=request.args.get('busca_sup', ''),
            pagina_area=pagina_area,
            total_paginas_area=total_paginas_area,
            total_areas=total_areas,
            itens_por_pagina_area=itens_por_pagina,
            ordenar_area=ordenar_area,
            ordem_area=ordem_area,
            busca_area=request.args.get('busca_area', ''),
            erro_relatorio=erro_relatorio,
        )
    except Exception as e:
        logger.exception(f"Erro ao gerar relatórios: %s", e)
        try:
            # Tenta exibir a página de relatórios com dados vazios e mensagem de erro
            return render_template(
                'relatorios.html',
                relatorio={},
                ranking_gamificacao=[],
                metricas_gerais={},
                metricas_supervisores=[],
                metricas_supervisores_full=[],
                metricas_areas=[],
                metricas_areas_full=[],
                insights=[],
                data_geracao=None,
                pagina_sup=1,
                total_paginas_sup=1,
                total_supervisores=0,
                itens_por_pagina_sup=max(1, int(getattr(Config, 'ITENS_POR_PAGINA', 10))),
                ordenar_sup='desc',
                ordem_sup='desc',
                busca_sup=request.args.get('busca_sup', ''),
                pagina_area=1,
                total_paginas_area=1,
                total_areas=0,
                itens_por_pagina_area=max(1, int(getattr(Config, 'ITENS_POR_PAGINA', 10))),
                ordenar_area='desc',
                ordem_area='desc',
                busca_area=request.args.get('busca_area', ''),
                erro_relatorio=True,
            )
        except Exception as e2:
            logger.exception("Erro ao renderizar página de relatórios (fallback): %s", e2)
            flash_t('error_generating_reports', 'danger')
            return redirect(url_for('main.admin'))


@main.route('/admin/indices-firestore')
@login_required
@requer_perfil('admin')
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
