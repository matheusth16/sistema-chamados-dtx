"""Rotas do painel administrativo: dashboard, exportar, histórico, relatórios."""

import io
import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from flask import (
    Response,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_login import current_user, login_required

from app.cache import get_static_cached
from app.db.models.chamado import ChamadoRow
from app.decoradores import requer_gestor_ou_admin, requer_supervisor_area
from app.i18n import flash_t, get_translation
from app.limiter import limiter
from app.models import Chamado
from app.models_categorias import CategoriaSetor
from app.models_historico import Historico
from app.models_usuario import Usuario
from app.routes import main
from app.services.analytics import analisador
from app.services.contadores_uso import (
    verificar_e_incrementar_export,
    verificar_e_incrementar_relatorio,
)
from app.services.dashboard_service import (
    _filtrar_chamados_por_permissao,
    obter_contexto_admin,
    ordenar_metricas_areas,
    ordenar_metricas_supervisores,
    preparar_metricas_paginadas,
)
from app.services.excel_export_service import MAX_EXPORT_CHAMADOS, _safe_cell
from app.services.filters import aplicar_filtros_dashboard_com_paginacao
from app.services.gestor_dashboard_service import obter_contexto_gestor_dashboard
from app.services.permissions import usuario_pode_operar_chamado, usuario_pode_ver_chamado
from app.services.permissoes_edicao_chamado import (
    chamado_aceita_transicao_status,
    filtrar_supervisores_por_area,
    montar_anexos_para_exibicao,
    montar_flags_detalhe_chamado,
)
from app.services.status_service import atualizar_status_chamado
from app.utils import formatar_data_para_excel
from config import Config

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


def _dashboard_endpoint() -> str:
    """Retorna o endpoint de dashboard correto para o perfil atual."""
    if current_user.perfil == "supervisor":
        return "main.painel"
    return "main.admin"


def _redirect_dashboard(**kwargs) -> Response:
    return redirect(url_for(_dashboard_endpoint(), **kwargs))


def _query_chamados_escopada_por_area(user):
    """Condições de escopo de chamados por área, quando o usuário é supervisor.

    Mesmo filtro que obter_contexto_admin já aplica pro /painel — sem isso,
    rotas que consultam chamados direto (ex.: exportações) trazem
    chamados/métricas de áreas que não são do supervisor.
    """
    condicoes = []
    if user.perfil == "supervisor" and getattr(user, "areas", None):
        condicoes.append(ChamadoRow.supervisor_ids_com_acesso.contains([user.id]))
    return condicoes


def _render_dashboard() -> Response:
    """Lógica compartilhada de dashboard — chamada por admin() e painel()."""
    if request.method == "POST":
        # Gestor read-only: bloquear mutação de status via formulário do dashboard
        if getattr(current_user, "is_gestor_only", False):
            flash_t("access_denied_profiles", "danger", profiles="gestor")
            return redirect(url_for("main.gestor_dashboard"))
        chamado_id = request.form.get("chamado_id")
        novo_status = request.form.get("novo_status")
        logger.debug("Alterar status: chamado_id=%s, novo_status=%s", chamado_id, novo_status)
        try:
            chamado_obj = Chamado.get_by_id(chamado_id)
            if chamado_obj is None:
                flash_t("ticket_not_found", "danger")
                return _redirect_dashboard(**request.args)
            data_anterior = chamado_obj.to_dict()

            if current_user.perfil == "supervisor" and not usuario_pode_operar_chamado(
                current_user, chamado_obj
            ):
                flash_t("only_update_tickets_your_area", "danger")
                return _redirect_dashboard(**request.args)

            pode_trans, _ = chamado_aceita_transicao_status(current_user, chamado_obj, novo_status)
            if not pode_trans:
                flash_t("error_ticket_frozen_no_edit", "danger")
                return _redirect_dashboard(**request.args)

            resultado = atualizar_status_chamado(
                chamado_id=chamado_id,
                novo_status=novo_status,
                usuario_id=current_user.id,
                usuario_nome=current_user.nome,
                data_chamado=data_anterior,
            )
            if resultado["sucesso"]:
                flash(resultado["mensagem"], "success")
            else:
                if "erro" in resultado:
                    flash(resultado["erro"], "danger")
                else:
                    flash_t("error_updating", "danger")
            return _redirect_dashboard(**request.args)
        except Exception as e:
            logger.exception("Erro ao atualizar chamado %s: %s", chamado_id, e)
            flash_t("error_updating_with_msg", "danger", error=str(e))
            return _redirect_dashboard(**request.args)

    itens_por_pagina = Config.ITENS_POR_PAGINA_DASHBOARD
    contexto = obter_contexto_admin(current_user, request.args, itens_por_pagina=itens_por_pagina)
    setores = [
        s
        for s in get_static_cached("categorias_setor", CategoriaSetor.get_all, ttl_seconds=1800)
        if getattr(s, "ativo", True)
    ]
    return render_template("dashboard.html", **contexto, setores=setores)


@main.route("/gestor/dashboard", methods=["GET"])
@login_required
@requer_gestor_ou_admin
def gestor_dashboard() -> Response:
    """Dashboard gerencial read-only (Fase 5). Acessível por gestores e admins."""
    filtro = request.args.get("filtro")
    contexto = obter_contexto_gestor_dashboard(filtro=filtro, usuario=current_user)
    return render_template("gestor_dashboard.html", **contexto)


@main.route("/admin", methods=["GET", "POST"])
@requer_supervisor_area
def admin() -> Response:
    """Dashboard principal para admin. Supervisores são redirecionados a /painel."""
    if current_user.perfil == "supervisor":
        return redirect(url_for("main.painel", **request.args))
    return _render_dashboard()


@main.route("/painel", methods=["GET", "POST"])
@requer_supervisor_area
def painel() -> Response:
    """Dashboard para supervisores. Admins são redirecionados a /admin."""
    if current_user.perfil in ("admin", "admin_global"):
        return redirect(url_for("main.admin", **request.args))
    # Gestor read-only: redirecionar para dashboard gerencial (GET e POST)
    if getattr(current_user, "is_gestor_only", False):
        return redirect(url_for("main.gestor_dashboard"))
    return _render_dashboard()


@main.route("/chamado/<chamado_id>")
@login_required
def visualizar_detalhe_chamado(chamado_id: str) -> Response:
    """Exibe detalhes do chamado. Solicitante vê só os próprios; supervisor/admin conforme permissão."""
    try:
        chamado = Chamado.get_by_id(chamado_id)
        if chamado is None:
            flash_t("ticket_not_found", "danger")
            return redirect(
                url_for(_dashboard_endpoint())
                if current_user.perfil in ("supervisor", "admin")
                else url_for("main.meus_chamados")
            )
        if not usuario_pode_ver_chamado(current_user, chamado):
            if current_user.perfil == "solicitante":
                flash_t("ticket_not_found", "danger")
                return redirect(url_for("main.meus_chamados"))
            flash_t("only_view_history_your_area", "danger")
            return _redirect_dashboard()

        from app.services.visualizacao_chamado_service import (
            marcar_visualizado_pelo_responsavel,
        )

        marcar_visualizado_pelo_responsavel(chamado, current_user.id)

        voltar_url = (
            request.referrer
            if request.referrer and _same_origin(request.referrer)
            else (
                url_for(_dashboard_endpoint())
                if current_user.perfil in ("supervisor", "admin")
                else url_for("main.meus_chamados")
            )
        )
        flags = montar_flags_detalhe_chamado(current_user, chamado)

        usuarios_gestao = get_static_cached("usuarios_all", Usuario.get_all, ttl_seconds=300)
        supervisores_list = [u for u in usuarios_gestao if u.perfil == "supervisor" and u.nome]
        if flags["pode_editar_base"]:
            supervisores_list = filtrar_supervisores_por_area(current_user, supervisores_list)
        supervisores_detalhados = (
            sorted(
                [{"id": u.id, "nome": u.nome, "area": u.area} for u in supervisores_list],
                key=lambda x: (x["nome"] or "").upper(),
            )
            if flags["pode_editar_base"]
            else []
        )
        setores = [
            s
            for s in get_static_cached("categorias_setor", CategoriaSetor.get_all, ttl_seconds=1800)
            if getattr(s, "ativo", True)
        ]

        historico = Historico.get_by_chamado_id(chamado.id)
        anexos_exibicao = montar_anexos_para_exibicao(chamado, historico)

        from app.services.previsao_atendimento_service import (
            calcular_sugestao_extensao_automatica,
            obter_solicitacao_pendente,
            usuario_pode_decidir_previsao_atendimento,
        )

        previsao_pendente = obter_solicitacao_pendente(chamado.id)
        pode_decidir_previsao = previsao_pendente is not None and (
            usuario_pode_decidir_previsao_atendimento(current_user, chamado.area or "")
        )
        # Botão único "Solicitar nova previsão de atendimento": se elegível,
        # o modal já vem com a data de extensão automática pré-preenchida —
        # ver calcular_sugestao_extensao_automatica.
        sugestao_extensao = calcular_sugestao_extensao_automatica(chamado.id)
        # min do campo de data — trava no navegador o mesmo limite que o
        # service já rejeita (previsao <= agora não é permitido, ver
        # solicitar_previsao_atendimento): evita a pessoa escolher a data de
        # hoje ou uma data passada só pra descobrir o erro depois de enviar.
        previsao_min = datetime.now(ZoneInfo(Config.SLA_TIMEZONE)).strftime("%Y-%m-%dT%H:%M")

        # Conversa solicitante↔responsável: só as respostas em texto livre,
        # em ordem cronológica (historico vem mais recente primeiro).
        mensagens_conversa = [
            h for h in historico if h.acao in ("resposta_solicitante", "resposta_responsavel")
        ]
        mensagens_conversa.reverse()

        # Cursor único do polling da tela de detalhe (Conversa + "chamado
        # atualizado", ver api_mensagens_novas_chamado): maior Historico.id
        # deste chamado no momento do render, não só o da última mensagem —
        # senão uma mudança não-conversa já refletida na página (ex.: status)
        # dispararia o aviso de "atualizado" na hora, à toa.
        cursor_inicial_chamado = max((h.id or 0 for h in historico), default=0)

        from app.services.traducao_conteudo_service import montar_traducoes_chamado

        # Lote único (descrição/motivo_* + todo o histórico) — 1 lookup de
        # cache em lote; HTTP ao LibreTranslate 1 por texto que faltar no
        # cache (nunca em array — ver traducao_conteudo_service.py).
        traducoes = montar_traducoes_chamado(chamado, historico, session.get("language", "en"))

        return render_template(
            "visualizar_chamado.html",
            chamado=chamado,
            voltar_url=voltar_url,
            cursor_inicial_chamado=cursor_inicial_chamado,
            traducoes=traducoes,
            pode_editar=flags["pode_editar"],
            pode_editar_descricao=flags["pode_editar_descricao"],
            nivel_congelamento=flags["nivel_congelamento"],
            supervisores_detalhados=supervisores_detalhados,
            setores=setores,
            pode_editar_descricao_solicitante=flags["pode_editar_descricao_solicitante"],
            segundos_restantes_edicao=flags["segundos_restantes_edicao"],
            pode_cancelar_solicitante=flags["pode_cancelar_solicitante"],
            pode_anexo_tardio_solicitante=flags["pode_anexo_tardio_solicitante"],
            anexos_exibicao=anexos_exibicao,
            previsao_pendente=previsao_pendente,
            pode_decidir_previsao=pode_decidir_previsao,
            mensagens_conversa=mensagens_conversa,
            sugestao_extensao=sugestao_extensao,
            previsao_min=previsao_min,
        )
    except Exception as e:
        logger.exception("Erro ao exibir chamado %s: %s", chamado_id, e)
        flash_t("ticket_not_found", "danger")
        return redirect(
            url_for(_dashboard_endpoint())
            if current_user.perfil in ("supervisor", "admin")
            else url_for("main.meus_chamados")
        )


@main.route("/chamado/editar", methods=["POST"])
@login_required
def editar_chamado_pagina() -> Response:
    """Processa o formulário de edição da página de detalhes do chamado (status, responsável, descrição, anexo)."""
    if not current_user.is_supervisor_or_above:
        flash_t("only_supervisor_can_edit", "danger")
        return redirect(url_for("main.index"))

    # Gestor read-only não pode editar chamados
    if getattr(current_user, "is_gestor_only", False):
        flash_t("access_denied_profiles", "danger", profiles="gestor")
        return redirect(url_for("main.gestor_dashboard"))

    chamado_id = request.form.get("chamado_id")
    if not chamado_id:
        flash_t("ticket_not_found", "danger")
        return _redirect_dashboard()

    chamado = Chamado.get_by_id(chamado_id)
    if chamado is None:
        flash_t("ticket_not_found", "danger")
        return _redirect_dashboard()

    if not usuario_pode_ver_chamado(current_user, chamado):
        flash_t("only_view_history_your_area", "danger")
        return _redirect_dashboard()

    from app.services.edicao_chamado_service import processar_edicao_chamado

    setores_adicionais_form = request.form.getlist("setores_adicionais")

    resultado = processar_edicao_chamado(
        usuario_atual=current_user,
        chamado_id=chamado_id,
        novo_status=request.form.get("novo_status"),
        motivo_cancelamento=(request.form.get("motivo_cancelamento") or "").strip(),
        nova_descricao=request.form.get("nova_descricao", ""),
        novo_responsavel_id=(request.form.get("novo_responsavel_id") or "").strip(),
        novo_sla_str=(request.form.get("sla_dias") or "").strip(),
        arquivos_novos=request.files.getlist("anexos_novos"),
        setores_adicionais_lista=setores_adicionais_form,
    )

    if resultado.get("sucesso"):
        lang = session.get("language", "en")
        mensagem = resultado.get("mensagem") or get_translation("changes_saved", lang)
        flash(mensagem, "success")
    else:
        erro = resultado.get("erro", "")
        if erro:
            flash(erro, "danger")
        else:
            flash_t("error_server", "danger")

    return redirect(url_for("main.visualizar_detalhe_chamado", chamado_id=chamado_id))


@main.route("/chamado/<chamado_id>/historico")
@login_required
def visualizar_historico(chamado_id: str) -> Response:
    """Exibe histórico de alterações do chamado.

    Solicitantes "puros" (sem nivel_gestao) que chegam por link de e-mail
    antigo são redirecionados para a página de detalhe do chamado (onde fica
    o bloco de confirmação). Quem tem nivel_gestao (Gestor do Setor/Gerente
    de Produção/Assistente GM/GM) passa direto mesmo com perfil='solicitante'
    — achado 2026-08-17: o gate antigo redirecionava QUALQUER perfil
    'solicitante' antes de checar nivel_gestao, bloqueando esses gestores.
    """
    if current_user.perfil == "solicitante" and not current_user.is_gestor:
        return redirect(url_for("main.visualizar_detalhe_chamado", chamado_id=chamado_id))

    if not (current_user.is_supervisor_or_above or current_user.is_gestor):
        flash_t("access_denied_supervisors", "danger")
        return redirect(url_for("main.index"))

    try:
        chamado = Chamado.get_by_id(chamado_id)
        if chamado is None:
            flash_t("ticket_not_found", "danger")
            return _redirect_dashboard()
        if not usuario_pode_ver_chamado(current_user, chamado):
            flash_t("only_view_history_your_area", "danger")
            return _redirect_dashboard()
        # Get_by_chamado_id vem mais recente primeiro; a tela de histórico
        # mostra em ordem cronológica (mais antigo/criação no topo, mais
        # recente embaixo) — pedido do usuário, 2026-08-20.
        historico = list(reversed(Historico.get_by_chamado_id(chamado_id)))

        from app.services.traducao_conteudo_service import montar_traducoes_chamado

        traducoes = montar_traducoes_chamado(chamado, historico, session.get("language", "en"))

        return render_template(
            "historico.html", chamado=chamado, historico=historico, traducoes=traducoes
        )
    except Exception as e:
        logger.exception("Erro ao buscar histórico de %s: %s", chamado_id, e)
        flash_t("error_loading_history", "danger")
        return _redirect_dashboard()


@main.route("/exportar")
@requer_supervisor_area
@limiter.limit("10 per hour")
def exportar() -> Response:
    """Exporta chamados filtrados para Excel (até MAX_EXPORT_CHAMADOS)."""
    limite_export = getattr(Config, "EXPORT_EXCEL_MAX_POR_USUARIO_POR_DIA", 0) or 0
    if limite_export > 0:
        pode, msg = verificar_e_incrementar_export(current_user.id, limite_export)
        if not pode:
            if msg:
                flash(msg, "warning")
            flash_t("error_exporting_data", "danger")
            return _redirect_dashboard()
    try:
        condicoes_base = _query_chamados_escopada_por_area(current_user)
        resultado = aplicar_filtros_dashboard_com_paginacao(
            condicoes_base, request.args, limite=MAX_EXPORT_CHAMADOS, cursor=None
        )
        docs = resultado["docs"]
        chamados = _filtrar_chamados_por_permissao(docs, current_user)

        dados: list[dict[str, Any]] = []
        for c in chamados:
            dados.append(
                {
                    "Chamado": c.numero_chamado,
                    "Categoria": c.categoria,
                    "RL": c.rl_codigo or "-",
                    "Tipo": c.tipo_solicitacao,
                    "Gate": c.gate or "-",
                    "Responsável": c.responsavel,
                    "Solicitante": c.solicitante_nome or "-",
                    "Área": c.area or "-",
                    "Status": c.status,
                    "Anexo": c.anexo or "-",
                    "Abertura": formatar_data_para_excel(c.data_abertura),
                    "Conclusão": formatar_data_para_excel(c.data_conclusao),
                    "Descrição": c.descricao,
                }
            )
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Chamados"
        if dados:
            ws.append(list(dados[0].keys()))
            for row in dados:
                ws.append([_safe_cell(v) for v in row.values()])
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"relatorio_chamados_{ts}.xlsx",
        )
    except Exception as e:
        logger.exception("Erro ao exportar: %s", e)
        flash_t("error_exporting_data", "danger")
        return _redirect_dashboard()


@main.route("/exportar-avancado")
@requer_supervisor_area
@limiter.limit("5 per hour")
def exportar_avancado() -> Response:
    """Exporta relatório completo em Excel com múltiplas abas (até MAX_EXPORT_CHAMADOS)."""
    limite_export = getattr(Config, "EXPORT_EXCEL_MAX_POR_USUARIO_POR_DIA", 0) or 0
    if limite_export > 0:
        pode, msg = verificar_e_incrementar_export(current_user.id, limite_export)
        if not pode:
            if msg:
                flash(msg, "warning")
            flash_t("error_exporting_report", "danger")
            return _redirect_dashboard()
    try:
        from app.services.excel_export_service import exportador_excel

        # Busca chamados com filtros e permissão (limitado por MAX_EXPORT_CHAMADOS)
        condicoes_base = _query_chamados_escopada_por_area(current_user)
        resultado = aplicar_filtros_dashboard_com_paginacao(
            condicoes_base, request.args, limite=MAX_EXPORT_CHAMADOS, cursor=None
        )
        docs = resultado["docs"]
        chamados = _filtrar_chamados_por_permissao(docs, current_user)

        # Métricas gerais/agregadas: analisador consulta a coleção inteira sem
        # escopo de área — supervisor não-admin só pode ver métricas/nomes de
        # supervisores da(s) própria(s) área(s), senão vaza dado de outras áreas.
        if current_user.is_admin_or_above:
            metricas_gerais = analisador.obter_metricas_gerais(dias=30)
            metricas_supervisores = analisador.obter_metricas_supervisores()
        else:
            chamados_pre_carregados = [c.to_dict() for c in chamados]
            metricas_gerais = analisador.obter_metricas_gerais(
                dias=30, chamados_pre_carregados=chamados_pre_carregados
            )
            areas_usuario = set(getattr(current_user, "areas", None) or [])
            metricas_supervisores = [
                m
                for m in analisador.obter_metricas_supervisores(
                    chamados_pre_carregados=chamados_pre_carregados
                )
                if m.get("area") in areas_usuario
            ]

        # Filtros aplicados (para documentar no Excel) — chaves traduzidas no idioma da sessão
        lang = session.get("language", "en")
        filtros_aplicados = {}
        if request.args.get("search"):
            filtros_aplicados[get_translation("excel_filter_search", lang)] = request.args.get(
                "search"
            )
        if request.args.get("categoria"):
            filtros_aplicados[get_translation("category", lang)] = request.args.get("categoria")
        if request.args.get("status"):
            filtros_aplicados[get_translation("status", lang)] = request.args.get("status")
        if request.args.get("responsavel"):
            filtros_aplicados[get_translation("responsible", lang)] = request.args.get(
                "responsavel"
            )

        # Exporta relatório
        output = exportador_excel.exportar_relatorio_completo(
            chamados=chamados,
            metricas_gerais=metricas_gerais,
            metricas_supervisores=metricas_supervisores,
            filtros_aplicados=filtros_aplicados,
            language=lang,
        )

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"relatorio_completo_{ts}.xlsx",
        )
    except Exception as e:
        logger.exception("Erro ao exportar relatório avançado: %s", e)
        flash_t("error_exporting_report", "danger")
        return _redirect_dashboard()


DIAS_PERIODO_PERMITIDOS = (7, 30, 90)


@main.route("/admin/relatorios")
@login_required
@requer_gestor_ou_admin
def relatorios() -> Response:
    """Dashboard de relatórios e análises. Acessível a admins e a quem tem
    nivel_gestao — supervisor "puro" (sem nivel_gestao) não vê essa página.
    Gestor do Setor (nivel_gestao='gestor_setor') só vê o relatório da própria
    área; demais níveis de gestão (gerente_producao/assistente_gm/gm) e admins
    veem o relatório completo (todas as áreas).
    Use ?atualizar=1 para forçar dados frescos.
    Query params: dias (7|30|90, padrão 30), pagina_sup, pagina_area, ordenar_sup,
    ordenar_area, ordem_sup, ordem_area (asc|desc), busca_sup, busca_area."""
    erro_relatorio = False
    try:
        dias = request.args.get("dias", 30, type=int)
        if dias not in DIAS_PERIODO_PERMITIDOS:
            dias = 30
        areas_escopo = (
            list(current_user.areas or [])
            if getattr(current_user, "nivel_gestao", None) == "gestor_setor"
            else None
        )
        atualizar = request.args.get("atualizar") == "1"
        if atualizar:
            limite = getattr(Config, "RELATORIO_MAX_POR_USUARIO_POR_DIA", 0) or 0
            if limite > 0:
                pode, msg = verificar_e_incrementar_relatorio(current_user.id, limite)
                if not pode:
                    flash_t("generic_error", "danger")
                    if msg:
                        flash(msg, "warning")
                    return redirect(url_for("main.relatorios", dias=dias))
        try:
            relatorio = (
                analisador.obter_relatorio_completo(
                    usar_cache=not atualizar, dias=dias, areas=areas_escopo
                )
                or {}
            )
        except Exception as e_analytics:
            logger.exception("Erro ao obter relatório completo (analytics): %s", e_analytics)
            relatorio = {
                "data_geracao": None,
                "metricas_gerais": {},
                "metricas_supervisores": [],
                "metricas_areas": [],
                "insights": [],
            }
            erro_relatorio = True
        insights = list(relatorio.get("insights") or [])
        ordem_tipo = {"aviso": 0, "sucesso": 1, "info": 2}
        insights = sorted(insights, key=lambda x: ordem_tipo.get((x or {}).get("tipo"), 3))

        itens_por_pagina = max(1, int(getattr(Config, "ITENS_POR_PAGINA", 10)))

        # Supervisores: filtrar, ordenar e paginar via serviço
        sup_lista_raw = list(relatorio.get("metricas_supervisores") or [])
        busca_sup = (request.args.get("busca_sup") or "").strip().lower()
        if busca_sup:
            sup_lista_raw = [
                s
                for s in sup_lista_raw
                if busca_sup in (s.get("supervisor_nome") or "").lower()
                or busca_sup in (s.get("supervisor_email") or "").lower()
                or busca_sup in (s.get("area") or "").lower()
            ]
        ordenar_sup = request.args.get("ordenar_sup") or "carga"
        ordem_sup = (request.args.get("ordem_sup") or "desc").lower()
        if ordem_sup not in ("asc", "desc"):
            ordem_sup = "desc"
        pag_sup = preparar_metricas_paginadas(
            sup_lista_raw,
            ordenar_sup,
            ordem_sup == "asc",
            request.args.get("pagina_sup", 1, type=int),
            itens_por_pagina,
            ordenar_metricas_supervisores,
        )
        metricas_supervisores = pag_sup["items"]
        metricas_supervisores_full = pag_sup["items_full"]
        pagina_sup = pag_sup["pagina"]
        total_supervisores = pag_sup["total"]
        total_paginas_sup = pag_sup["total_paginas"]

        # Áreas: filtrar, ordenar e paginar via serviço
        area_lista_raw = list(relatorio.get("metricas_areas") or [])
        busca_area = (request.args.get("busca_area") or "").strip().lower()
        if busca_area:
            area_lista_raw = [
                a for a in area_lista_raw if busca_area in (a.get("area") or "").lower()
            ]
        ordenar_area = request.args.get("ordenar_area") or "total"
        ordem_area = (request.args.get("ordem_area") or "desc").lower()
        if ordem_area not in ("asc", "desc"):
            ordem_area = "desc"
        pag_area = preparar_metricas_paginadas(
            area_lista_raw,
            ordenar_area,
            ordem_area == "asc",
            request.args.get("pagina_area", 1, type=int),
            itens_por_pagina,
            ordenar_metricas_areas,
        )
        metricas_areas = pag_area["items"]
        metricas_areas_full = pag_area["items_full"]
        pagina_area = pag_area["pagina"]
        total_areas = pag_area["total"]
        total_paginas_area = pag_area["total_paginas"]

        # Ranking Gamificação Top 3 da Semana
        # Aproveitar os usuários puxados do banco ou base no relatorio
        usuarios_gestao = get_static_cached("usuarios_all", Usuario.get_all, ttl_seconds=300)
        ranking_gamificacao = sorted(
            [
                u
                for u in usuarios_gestao
                if u.exp_semanal > 0 and u.perfil in ("supervisor", "admin") and u.nome
            ],
            key=lambda u: u.exp_semanal,
            reverse=True,
        )[:3]

        # Áreas: lista completa (para traduções no front-end)
        setores = [
            s
            for s in get_static_cached("categorias_setor", CategoriaSetor.get_all, ttl_seconds=1800)
            if getattr(s, "ativo", True)
        ]

        return render_template(
            "relatorios.html",
            relatorio=relatorio,
            ranking_gamificacao=ranking_gamificacao,
            metricas_gerais=relatorio.get("metricas_gerais") or {},
            metricas_delta=relatorio.get("metricas_delta") or {},
            metricas_supervisores=metricas_supervisores,
            metricas_supervisores_full=metricas_supervisores_full,
            metricas_areas=metricas_areas,
            metricas_areas_full=metricas_areas_full,
            insights=insights,
            data_geracao=relatorio.get("data_geracao"),
            pagina_sup=pagina_sup,
            total_paginas_sup=total_paginas_sup,
            total_supervisores=total_supervisores,
            itens_por_pagina_sup=itens_por_pagina,
            ordenar_sup=ordenar_sup,
            ordem_sup=ordem_sup,
            busca_sup=request.args.get("busca_sup", ""),
            pagina_area=pagina_area,
            total_paginas_area=total_paginas_area,
            total_areas=total_areas,
            itens_por_pagina_area=itens_por_pagina,
            ordenar_area=ordenar_area,
            ordem_area=ordem_area,
            busca_area=request.args.get("busca_area", ""),
            erro_relatorio=erro_relatorio,
            setores=setores,
            dias=dias,
        )
    except Exception as e:
        logger.exception("Erro ao gerar relatórios: %s", e)
        try:
            # Tenta exibir a página de relatórios com dados vazios e mensagem de erro
            setores = [
                s
                for s in get_static_cached(
                    "categorias_setor", CategoriaSetor.get_all, ttl_seconds=1800
                )
                if getattr(s, "ativo", True)
            ]
            return render_template(
                "relatorios.html",
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
                itens_por_pagina_sup=max(1, int(getattr(Config, "ITENS_POR_PAGINA", 10))),
                ordenar_sup="desc",
                ordem_sup="desc",
                busca_sup=request.args.get("busca_sup", ""),
                pagina_area=1,
                total_paginas_area=1,
                total_areas=0,
                itens_por_pagina_area=max(1, int(getattr(Config, "ITENS_POR_PAGINA", 10))),
                ordenar_area="desc",
                ordem_area="desc",
                busca_area=request.args.get("busca_area", ""),
                erro_relatorio=True,
                setores=setores,
                dias=request.args.get("dias", 30, type=int)
                if request.args.get("dias", 30, type=int) in DIAS_PERIODO_PERMITIDOS
                else 30,
            )
        except Exception as e2:
            logger.exception("Erro ao renderizar página de relatórios (fallback): %s", e2)
            flash_t("error_generating_reports", "danger")
            return _redirect_dashboard()
