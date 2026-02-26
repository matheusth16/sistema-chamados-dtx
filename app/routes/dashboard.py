"""Rotas do painel administrativo: dashboard, exportar, histórico, relatórios, índices."""
import logging
import io
from datetime import datetime
from typing import List, Dict, Any
from flask import render_template, request, redirect, url_for, send_file, flash, Response, current_app
from urllib.parse import urlparse
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
from app.services.upload import salvar_anexo
from app.firebase_retry import execute_with_retry
from app.models_categorias import CategoriaGate

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

    # Ranking Gamificação (Top 5 da Semana)
    # Pegamos os usuários logados/ativos (ideal buscar do banco filtrando por exp_semanal > 0, mas em memória resolve se a base não for tão monstruosa de técnicos)
    # Como não temos uma query que retorna *todos* sempre ou dependemos de criptografia (já lidada em get_all),
    # reaproveitamos usuarios_gestao que já possui supervisores/admins
    ranking_gamificacao = sorted(
        [u for u in usuarios_gestao if u.exp_semanal > 0],
        key=lambda u: u.exp_semanal, 
        reverse=True
    )[:5]

    chamados_ref = db.collection('chamados')
    # Supervisor vê apenas chamados das suas áreas (filtro no Firestore para não trazer outros setores)
    if current_user.perfil == 'supervisor' and getattr(current_user, 'areas', None):
        areas = current_user.areas[:10]  # Firestore 'in' aceita no máximo 10
        if areas:
            chamados_ref = chamados_ref.where('area', 'in', areas)
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
        ranking_gamificacao=ranking_gamificacao,
        max=max,
        min=min,
    )


@main.route('/chamado/<chamado_id>')
@login_required
@limiter.limit("60 per minute")
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
        supervisores_detalhados = sorted(
            [{'id': u.id, 'nome': u.nome, 'area': u.area} for u in usuarios_gestao if u.perfil in ('supervisor', 'admin') and u.nome],
            key=lambda x: (x['nome'] or '').upper()
        ) if pode_editar else []
        return render_template(
            'visualizar_chamado.html',
            chamado=chamado,
            voltar_url=voltar_url,
            pode_editar=pode_editar,
            supervisores_detalhados=supervisores_detalhados
        )
    except Exception as e:
        logger.exception("Erro ao exibir chamado %s: %s", chamado_id, e)
        flash_t('ticket_not_found', 'danger')
        return redirect(url_for('main.admin' if current_user.perfil in ('supervisor', 'admin') else 'main.meus_chamados'))


@main.route('/chamado/editar', methods=['POST'])
@login_required
@limiter.limit("30 per minute")
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

    data_chamado = doc_chamado.to_dict()
    update_data = {}

    try:
        novo_status = request.form.get('novo_status')
        if novo_status and novo_status in ('Aberto', 'Em Atendimento', 'Concluído') and novo_status != data_chamado.get('status'):
            resultado = atualizar_status_chamado(
                chamado_id=chamado_id,
                novo_status=novo_status,
                usuario_id=current_user.id,
                usuario_nome=current_user.nome,
                data_chamado=data_chamado,
            )
            if resultado.get('sucesso'):
                flash(resultado.get('mensagem', 'Status atualizado.'), 'success')
            else:
                flash(resultado.get('erro', 'Erro ao atualizar status.'), 'danger')

        novo_responsavel_id = request.form.get('novo_responsavel_id', '').strip()
        if novo_responsavel_id and novo_responsavel_id != data_chamado.get('responsavel_id'):
            novo_resp = Usuario.get_by_id(novo_responsavel_id)
            if novo_resp:
                update_data['responsavel_id'] = novo_resp.id
                update_data['responsavel'] = novo_resp.nome
                update_data['area'] = (novo_resp.areas[0] if getattr(novo_resp, 'areas', None) else novo_resp.area or data_chamado.get('area'))
                Historico(
                    chamado_id=chamado_id,
                    usuario_id=current_user.id,
                    usuario_nome=current_user.nome,
                    acao='alteracao_dados',
                    campo_alterado='responsável',
                    valor_anterior=data_chamado.get('responsavel'),
                    valor_novo=novo_resp.nome
                ).save()

        nova_descricao = request.form.get('nova_descricao', '').strip()
        descricao_anterior = (data_chamado.get('descricao') or '').strip()
        if nova_descricao and nova_descricao != descricao_anterior:
            update_data['descricao'] = nova_descricao
            # Limita tamanho para não estourar Firestore (1 doc = 1MB)
            max_len = 3000
            Historico(
                chamado_id=chamado_id,
                usuario_id=current_user.id,
                usuario_nome=current_user.nome,
                acao='alteracao_dados',
                campo_alterado='descrição',
                valor_anterior=(descricao_anterior[:max_len] + ('...' if len(descricao_anterior) > max_len else '')),
                valor_novo=(nova_descricao[:max_len] + ('...' if len(nova_descricao) > max_len else ''))
            ).save()

        arquivo_anexo = request.files.get('anexo')
        if arquivo_anexo and arquivo_anexo.filename:
            caminho_anexo = salvar_anexo(arquivo_anexo)
            if caminho_anexo is None and current_app.config.get('ENV') == 'production':
                flash_t('error_attachment_upload_production', 'warning')
            elif caminho_anexo:
                anexos_existentes = data_chamado.get('anexos', [])
                anexo_principal = data_chamado.get('anexo')
                if anexo_principal and anexo_principal not in anexos_existentes:
                    anexos_existentes.insert(0, anexo_principal)
                anexos_existentes.append(caminho_anexo)
                update_data['anexos'] = anexos_existentes
                if not anexo_principal:
                    update_data['anexo'] = caminho_anexo
                Historico(
                    chamado_id=chamado_id,
                    usuario_id=current_user.id,
                    usuario_nome=current_user.nome,
                    acao='alteracao_dados',
                    campo_alterado='anexo',
                    valor_anterior='-',
                    valor_novo=caminho_anexo,
                    detalhe=arquivo_anexo.filename
                ).save()

        if update_data:
            execute_with_retry(
                db.collection('chamados').document(chamado_id).update,
                update_data,
                max_retries=3
            )
            if not (novo_status and novo_status != data_chamado.get('status')):
                flash('Alterações salvas.', 'success')
    except Exception as e:
        logger.exception("Erro ao editar chamado na página: %s", e)
        flash_t('error_updating_with_msg', 'danger', error=str(e))

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
@limiter.limit("30 per minute")
def relatorios() -> Response:
    """Dashboard de relatórios e análises. Use ?atualizar=1 para forçar dados frescos.
    Query params: pagina_sup, pagina_area, ordenar_sup, ordenar_area, ordem_sup, ordem_area (asc|desc), busca_sup, busca_area."""
    erro_relatorio = False
    try:
        atualizar = request.args.get('atualizar') == '1'
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

        return render_template(
            'relatorios.html',
            relatorio=relatorio,
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
