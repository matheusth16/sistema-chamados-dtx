"""
Serviço de Relatórios Semanais.

Toda sexta-feira às 10h (BRT) o APScheduler chama `enviar_relatorio_semanal()`.
A função busca chamados abertos/atrasados e envia e-mails diretamente para
cada supervisor e admin via Microsoft Graph API.
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

import pytz
from sqlalchemy import select

from app import db as db_module
from app.db.models.chamado import ChamadoRow
from app.i18n import get_translated_category, get_translated_sector, get_translated_status
from app.models import Chamado
from app.models_historico import Historico
from app.models_usuario import Usuario
from app.services.analytics import _to_datetime, obter_sla_para_exibicao
from app.services.gestor_escalonamento_service import (
    construir_mapa_gestor_setor,
    construir_mapa_niveis_superiores,
)
from app.services.notifications import (
    _base_url,
    _link_dashboard,
    enviar_email,
    notificar_responsavel_prazo_24h,
)
from config import Config

_SLA_EN = {
    "Em risco": "At risk",
    "Atrasado": "Overdue",
    "No prazo": "On time",
}

logger = logging.getLogger(__name__)

BRASILIA = pytz.timezone("America/Sao_Paulo")
MAX_DOCS = 1000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agora_brasilia() -> datetime:
    return datetime.now(BRASILIA)


def _formatar_data(ts: Any) -> str:
    dt = _to_datetime(ts)
    if not dt:
        return "—"
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(BRASILIA).strftime("%d/%m/%Y")


def _dias_aberto(ts: Any) -> int:
    dt = _to_datetime(ts)
    if not dt:
        return 0
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return max(0, (datetime.now(UTC) - dt).days)


# ---------------------------------------------------------------------------
# Busca de chamados
# ---------------------------------------------------------------------------


def buscar_chamados_abertos() -> list[dict[str, Any]]:
    """
    Retorna todos os chamados Abertos / Em Atendimento enriquecidos com SLA.
    """
    resultado: list[dict[str, Any]] = []
    try:
        with db_module.SessionLocal() as session:
            stmt = (
                select(ChamadoRow)
                .where(ChamadoRow.status.in_(("Aberto", "Em Atendimento")))
                .limit(MAX_DOCS)
            )
            rows = session.execute(stmt).scalars().all()
    except Exception as exc:
        logger.exception("Erro ao buscar chamados abertos: %s", exc)
        return resultado

    for row in rows:
        chamado = Chamado._from_row(row)
        sla_info = obter_sla_para_exibicao(chamado) or {}
        resultado.append(
            {
                "id": chamado.id,
                "numero": chamado.numero_chamado or chamado.id,
                "categoria": get_translated_category(chamado.categoria, "en")
                if chamado.categoria
                else "—",
                "tipo": chamado.tipo_solicitacao or "—",
                "area": chamado.area or "—",
                "responsavel": chamado.responsavel or "—",
                "responsavel_id": chamado.responsavel_id or "",
                "solicitante": chamado.solicitante_nome or "—",
                "status": chamado.status,
                "data_abertura_fmt": _formatar_data(chamado.data_abertura),
                "dias_aberto": _dias_aberto(chamado.data_abertura),
                "sla_label": sla_info.get("label", ""),
                "atrasado": sla_info.get("label") == "Atrasado",
                "sla_dias": chamado.sla_dias,
                "alerta_prazo_24h_enviado_em": chamado.alerta_prazo_24h_enviado_em,
            }
        )
    return resultado


def buscar_chamados_cancelados_semana() -> list[dict[str, Any]]:
    """Retorna chamados com status Cancelado cuja data_cancelamento caiu nos
    últimos 7 dias corridos.

    Usado só no resumo dos níveis superiores de gestão (gerente_producao,
    assistente_gm, gm) — visão executiva completa da semana, aberto E
    cancelado. Supervisor, admin e gestor_setor continuam só com os chamados
    abertos (fora de escopo do pedido).
    """
    resultado: list[dict[str, Any]] = []
    corte = datetime.now(UTC) - timedelta(days=7)
    try:
        with db_module.SessionLocal() as session:
            stmt = (
                select(ChamadoRow)
                .where(ChamadoRow.status == "Cancelado")
                .where(ChamadoRow.data_cancelamento >= corte)
                .limit(MAX_DOCS)
            )
            rows = session.execute(stmt).scalars().all()
    except Exception as exc:
        logger.exception("Erro ao buscar chamados cancelados da semana: %s", exc)
        return resultado

    for row in rows:
        chamado = Chamado._from_row(row)
        resultado.append(
            {
                "id": chamado.id,
                "numero": chamado.numero_chamado or chamado.id,
                "categoria": get_translated_category(chamado.categoria, "en")
                if chamado.categoria
                else "—",
                "tipo": chamado.tipo_solicitacao or "—",
                "area": chamado.area or "—",
                "responsavel": chamado.responsavel or "—",
                "responsavel_id": chamado.responsavel_id or "",
                "solicitante": chamado.solicitante_nome or "—",
                "status": chamado.status,
                "data_abertura_fmt": _formatar_data(chamado.data_abertura),
                "dias_aberto": _dias_aberto(chamado.data_abertura),
                "sla_label": "",
                "atrasado": False,
                "sla_dias": chamado.sla_dias,
            }
        )
    return resultado


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------


def _tabela_html(chamados: list[dict[str, Any]], link_base: str) -> str:
    """Gera tabela HTML com os chamados."""
    cabecalho = (
        "<tr style='background:#f3f4f6;'>"
        "<th style='padding:8px 10px;text-align:left;font-size:12px;'>Ticket</th>"
        "<th style='padding:8px 10px;text-align:left;font-size:12px;'>Category</th>"
        "<th style='padding:8px 10px;text-align:left;font-size:12px;'>Type</th>"
        "<th style='padding:8px 10px;text-align:left;font-size:12px;'>Assignee</th>"
        "<th style='padding:8px 10px;text-align:left;font-size:12px;'>Requester</th>"
        "<th style='padding:8px 10px;text-align:left;font-size:12px;'>Opened</th>"
        "<th style='padding:8px 10px;text-align:left;font-size:12px;'>Days</th>"
        "<th style='padding:8px 10px;text-align:left;font-size:12px;'>SLA</th>"
        "</tr>"
    )
    linhas = []
    for c in chamados:
        if c["atrasado"] or c.get("status") == "Cancelado":
            cor_sla = "#dc2626"
        elif c["sla_label"] == "Em risco":
            cor_sla = "#d97706"
        else:
            cor_sla = "#16a34a"
        dias_txt = f" ({c.get('sla_dias')}d)" if c.get("sla_dias") else ""
        sla_display = (
            _SLA_EN.get(c["sla_label"]) or get_translated_status(c["status"], "en") or c["status"]
        )
        badge = f'<span style="color:{cor_sla};font-weight:600;">{sla_display}{dias_txt}</span>'
        link = f"{link_base}/chamado/{c['id']}/historico" if link_base else ""
        numero_html = (
            f'<a href="{link}" style="color:#2563eb;text-decoration:none;">{c["numero"]}</a>'
            if link
            else c["numero"]
        )
        linhas.append(
            "<tr>"
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;">{numero_html}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;">{escape(str(c["categoria"]))}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;">{escape(str(c["tipo"]))}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;">{escape(str(c.get("responsavel") or "—"))}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;">{escape(str(c["solicitante"]))}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;">{escape(str(c["data_abertura_fmt"]))}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;">{c["dias_aberto"]}d</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;">{badge}</td>'
            "</tr>"
        )
    return (
        f'<table style="width:100%;border-collapse:collapse;">{cabecalho}{"".join(linhas)}</table>'
    )


def _corpo_supervisor(
    nome: str,
    chamados: list[dict[str, Any]],
    link_dash: str,
    link_base: str,
    data_ref: str,
) -> tuple[str, str]:
    """Retorna (html, texto) do relatório para um supervisor."""
    atrasados = [c for c in chamados if c["atrasado"]]
    outros = [c for c in chamados if not c["atrasado"]]

    secoes = ""
    if atrasados:
        secoes += (
            f'<h3 style="color:#dc2626;margin:24px 0 4px;">Overdue ({len(atrasados)})</h3>'
            '<p style="color:#6b7280;font-size:11px;margin:0 0 8px;">SLA exceeded — default: Projects 2 days / others 3 days (tickets with custom SLA apply their own deadline)</p>'
            + _tabela_html(atrasados, link_base)
        )
    if outros:
        secoes += (
            f'<h3 style="color:#2563eb;margin:24px 0 4px;">Open / In Progress ({len(outros)})</h3>'
            + _tabela_html(outros, link_base)
        )

    btn = (
        f'<a href="{link_dash}" style="background:#2563eb;color:white;padding:10px 20px;'
        f'text-decoration:none;border-radius:6px;display:inline-block;margin-top:20px;">Open dashboard</a>'
        if link_dash
        else ""
    )

    html = (
        '<div style="font-family:Arial,sans-serif;max-width:760px;">'
        f'<h2 style="color:#111827;">Weekly Report — {data_ref}</h2>'
        f"<p>Hello, <strong>{nome}</strong>.</p>"
        f"<p><strong>Total:</strong> {len(chamados)} &nbsp;|&nbsp; "
        f'<span style="color:#dc2626;">Overdue: {len(atrasados)}</span> &nbsp;|&nbsp; '
        f"Others: {len(outros)}</p>"
        f"{secoes}{btn}"
        '<p style="margin-top:24px;color:#9ca3af;font-size:11px;"><em>Andon</em></p>'
        "</div>"
    )

    linhas = [
        f"Weekly Report — {data_ref}",
        f"Hello, {nome}.",
        f"Total: {len(chamados)} | Overdue: {len(atrasados)} | Others: {len(outros)}",
        "",
    ]
    if atrasados:
        linhas.append("== OVERDUE ==")
        for c in atrasados:
            linhas.append(
                f"  {c['numero']} | {c['categoria']} | {c['solicitante']} | {c['data_abertura_fmt']} ({c['dias_aberto']}d)"
            )
    if outros:
        linhas.append("== OPEN / IN PROGRESS ==")
        for c in outros:
            linhas.append(
                f"  {c['numero']} | {c['categoria']} | {c['solicitante']} | {c['data_abertura_fmt']} ({c['dias_aberto']}d)"
            )

    return html, "\n".join(linhas)


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------


def enviar_relatorio_semanal() -> dict[str, Any]:
    """
    Busca chamados abertos/atrasados e envia um e-mail por supervisor direto via
    Microsoft Graph API (`enviar_email()` — sem relay/parsing de subject; resíduo
    de design anterior removido na auditoria 2026-08-06).

    Admins recebem um resumo consolidado (todas as áreas). Gestores de setor
    (`nivel_gestao == "gestor_setor"`) recebem um resumo consolidado só da
    própria área, via `_enviar_resumo_gestores_area`.

    Retorna dict: enviados, ignorados, erros, total_chamados, total_atrasados.
    """
    data_ref = _agora_brasilia().strftime("%d/%m/%Y")
    link_base = _base_url()
    link_dash = _link_dashboard()

    chamados = buscar_chamados_abertos()
    total_chamados = len(chamados)
    total_atrasados = sum(1 for c in chamados if c["atrasado"])

    logger.info(
        "Relatório semanal: %d abertos, %d atrasados",
        total_chamados,
        total_atrasados,
    )

    if not chamados:
        logger.info("Nenhum chamado aberto; relatório semanal não enviado.")
        return {
            "enviados": 0,
            "ignorados": 0,
            "erros": 0,
            "total_chamados": 0,
            "total_atrasados": 0,
        }

    grupos: dict[str, list] = defaultdict(list)
    for c in chamados:
        grupos[c["responsavel_id"]].append(c)

    ids_responsaveis = [rid for rid in grupos if rid]
    supervisores_map = Usuario.get_by_ids(ids_responsaveis)

    enviados = ignorados = erros = 0

    for responsavel_id, lista in grupos.items():
        if not responsavel_id:
            ignorados += len(lista)
            continue

        supervisor = supervisores_map.get(responsavel_id)
        if not supervisor or not getattr(supervisor, "email", None):
            # Todo responsável DEVE ter e-mail cadastrado (é o identificador de
            # login) — se isso dispara de verdade, é dado inconsistente, não
            # caso normal (achado da auditoria 2026-08-06: era logger.debug).
            logger.warning(
                "Supervisor %s sem e-mail cadastrado; relatório ignorado.", responsavel_id
            )
            ignorados += len(lista)
            continue

        email_sup = supervisor.email.strip()
        nome = supervisor.nome or email_sup
        assunto = f"Weekly ticket report — {data_ref}"

        html, texto = _corpo_supervisor(nome, lista, link_dash, link_base, data_ref)
        ok, err = enviar_email(email_sup, assunto, html, texto, importance="low")
        if ok:
            enviados += 1
            logger.info(
                "Relatório semanal enviado para supervisor %s (%d chamados)",
                email_sup,
                len(lista),
            )
        else:
            erros += 1
            logger.warning("Falha ao enviar relatório para supervisor %s: %s", email_sup, err)

    _enviar_resumo_admins(chamados, grupos, supervisores_map, data_ref, link_dash, link_base)
    _enviar_resumo_gestores_area(chamados, data_ref, link_dash, link_base)
    _enviar_resumo_niveis_superiores(chamados, data_ref, link_base)

    return {
        "enviados": enviados,
        "ignorados": ignorados,
        "erros": erros,
        "total_chamados": total_chamados,
        "total_atrasados": total_atrasados,
    }


def _enviar_resumo_admins(
    chamados: list[dict[str, Any]],
    grupos: dict[str, list],
    supervisores_map: dict[str, Any],
    data_ref: str,
    link_dash: str,
    link_base: str,
) -> None:
    """Envia resumo consolidado para cada admin (e admin_global) diretamente.

    admin_global herda tudo de admin em todo o resto do app (ver
    Usuario.is_admin_or_above) — filtrar só perfil == "admin" aqui deixava os
    admin_global sem nivel_gestao (não caem nos outros 2 grupos, que dependem
    desse eixo ortogonal) sem receber o relatório semanal nenhum (achado ao
    vivo em produção, 2026-08-21).
    """
    try:
        admins = [
            u
            for u in Usuario.get_all()
            if getattr(u, "perfil", "") in ("admin", "admin_global") and getattr(u, "email", None)
        ]
    except Exception as exc:
        logger.warning("Não foi possível obter admins: %s", exc)
        return

    if not admins:
        return

    atrasados = [c for c in chamados if c["atrasado"]]

    linhas_sup = []
    for resp_id, lista in sorted(grupos.items(), key=lambda x: -len(x[1])):
        sup = supervisores_map.get(resp_id) if resp_id else None
        nome_sup = (sup.nome if sup else None) or resp_id or "No assignee"
        n_atras = sum(1 for c in lista if c["atrasado"])
        cor = "#dc2626" if n_atras else "#16a34a"
        linhas_sup.append(
            "<tr>"
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;">{nome_sup}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;">{len(lista)}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;color:{cor};font-weight:600;">{n_atras}</td>'
            "</tr>"
        )

    tabela_sup = (
        '<table style="width:100%;border-collapse:collapse;">'
        '<tr style="background:#f3f4f6;">'
        '<th style="padding:8px 10px;text-align:left;font-size:12px;">Assignee</th>'
        '<th style="padding:8px 10px;text-align:left;font-size:12px;">Total</th>'
        '<th style="padding:8px 10px;text-align:left;font-size:12px;">Overdue</th>'
        "</tr>" + "".join(linhas_sup) + "</table>"
    )

    btn = (
        f'<a href="{link_dash}" style="background:#2563eb;color:white;padding:10px 20px;'
        f'text-decoration:none;border-radius:6px;display:inline-block;margin-top:20px;">Open dashboard</a>'
        if link_dash
        else ""
    )

    html_admin = (
        '<div style="font-family:Arial,sans-serif;max-width:760px;">'
        f'<h2 style="color:#111827;">Weekly Summary — {data_ref}</h2>'
        f"<p><strong>Total open:</strong> {len(chamados)} &nbsp;|&nbsp; "
        f'<span style="color:#dc2626;"><strong>Overdue:</strong> {len(atrasados)}</span></p>'
        '<h3 style="margin-top:20px;">By assignee</h3>'
        f"{tabela_sup}"
        f'<h3 style="color:#dc2626;margin-top:24px;">Overdue tickets ({len(atrasados)})</h3>'
        + (
            _tabela_html(atrasados, link_base)
            if atrasados
            else '<p style="color:#6b7280;">None.</p>'
        )
        + f"{btn}"
        '<p style="margin-top:24px;color:#9ca3af;font-size:11px;"><em>Andon</em></p>'
        "</div>"
    )

    for admin in admins:
        email_admin = admin.email.strip()
        assunto = f"Weekly consolidated report — {data_ref}"
        ok, err = enviar_email(email_admin, assunto, html_admin, importance="low")
        if ok:
            logger.info("Resumo semanal enviado para admin %s", email_admin)
        else:
            logger.warning("Falha ao enviar resumo para admin %s: %s", email_admin, err)


def _enviar_resumo_gestores_area(
    chamados: list[dict[str, Any]],
    data_ref: str,
    link_dash: str,
    link_base: str,
) -> None:
    """Envia resumo consolidado (só da própria área) para cada gestor_setor.

    Achado da auditoria 2026-08-06: o relatório semanal só chegava ao
    responsável do chamado e aos admins — o gestor da área (nivel_gestao ==
    "gestor_setor") não recebia nada. Reusa a mesma fonte de verdade de
    e-mails de gestor (`gestor_escalonamento_service.construir_mapa_gestor_setor`)
    já usada pela escalação de SLA, em vez de duplicar essa lógica.
    """
    mapa_gestor_setor = construir_mapa_gestor_setor()
    if not mapa_gestor_setor:
        return

    por_area: dict[str, list] = defaultdict(list)
    for c in chamados:
        por_area[c.get("area") or ""].append(c)

    for area, lista in por_area.items():
        email_gestor = mapa_gestor_setor.get(area)
        if not email_gestor:
            continue

        area_en = get_translated_sector(area, "en") if area else area
        atrasados = [c for c in lista if c["atrasado"]]
        html = (
            '<div style="font-family:Arial,sans-serif;max-width:760px;">'
            f'<h2 style="color:#111827;">Weekly Area Report — {escape(area_en)} — {data_ref}</h2>'
            f"<p><strong>Total open:</strong> {len(lista)} &nbsp;|&nbsp; "
            f'<span style="color:#dc2626;"><strong>Overdue:</strong> {len(atrasados)}</span></p>'
            + _tabela_html(lista, link_base)
            + (
                f'<a href="{link_dash}" style="background:#2563eb;color:white;padding:10px 20px;'
                f'text-decoration:none;border-radius:6px;display:inline-block;margin-top:20px;">'
                f"Open dashboard</a>"
                if link_dash
                else ""
            )
            + '<p style="margin-top:24px;color:#9ca3af;font-size:11px;"><em>Andon</em></p>'
            "</div>"
        )
        assunto = f"Weekly area report — {area_en} — {data_ref}"
        ok, err = enviar_email(email_gestor, assunto, html, importance="low")
        if ok:
            logger.info(
                "Relatório semanal (área) enviado para gestor_setor %s (%s, %d chamados)",
                email_gestor,
                area,
                len(lista),
            )
        else:
            logger.warning(
                "Falha ao enviar relatório de área para gestor_setor %s: %s", email_gestor, err
            )


NIVEL_LABEL_EN = {
    "gerente_producao": "Production Manager",
    "assistente_gm": "Assistant GM",
    "gm": "GM",
}


def _cards_resumo_html(
    total: int,
    atrasados: int,
    num_setores: int,
    setor_critico: str | None,
    cancelados: int = 0,
) -> str:
    """Tira estatística (cartões) usada no topo do resumo pros níveis
    superiores: total aberto, total atrasado, nº de setores, setor com mais
    chamados atrasados e cancelados na semana."""

    def _card(valor: str, rotulo: str, bg: str, cor_valor: str) -> str:
        return (
            f'<td style="background:{bg};border-radius:8px;padding:14px 10px;text-align:center;">'
            f'<div style="font-size:22px;font-weight:700;color:{cor_valor};line-height:1.2;">{valor}</div>'
            f'<div style="font-size:11px;color:#6b7280;margin-top:2px;">{rotulo}</div>'
            "</td>"
        )

    return (
        '<table style="width:100%;border-collapse:separate;border-spacing:8px 0;margin:16px 0 8px;">'
        "<tr>"
        + _card(str(total), "Total open", "#f3f4f6", "#111827")
        + _card(str(atrasados), "Overdue", "#fef2f2", "#dc2626")
        + _card(str(cancelados), "Cancelled", "#fef2f2", "#dc2626")
        + _card(str(num_setores), "Sectors", "#f3f4f6", "#111827")
        + _card(
            escape(setor_critico) if setor_critico else "—", "Most critical", "#fffbeb", "#d97706"
        )
        + "</tr></table>"
    )


def _enviar_resumo_niveis_superiores(
    chamados: list[dict[str, Any]],
    data_ref: str,
    link_base: str,
) -> None:
    """Envia resumo consolidado de todas as áreas, quebrado por setor no mesmo
    e-mail, para cada nivel_gestao company-wide (gerente_producao, assistente_gm,
    gm). Reusa a mesma fonte de verdade de e-mails de gestor
    (`gestor_escalonamento_service.construir_mapa_niveis_superiores`) já usada
    pela escalação de SLA, em vez de duplicar essa lógica. Sem ninguém cadastrado
    num nível, não envia nada pra esse nível.
    """
    mapa_niveis = construir_mapa_niveis_superiores()
    if not mapa_niveis:
        return

    por_area: dict[str, list] = defaultdict(list)
    for c in chamados:
        por_area[c.get("area") or ""].append(c)

    areas_ordenadas = sorted(
        por_area.items(),
        key=lambda item: get_translated_sector(item[0], "en") if item[0] else item[0],
    )

    secoes = ""
    total_atrasados = 0
    setor_critico = None
    max_atrasados_setor = 0
    for area, lista in areas_ordenadas:
        area_en = get_translated_sector(area, "en") if area else "No sector"
        atrasados_area = sum(1 for c in lista if c["atrasado"])
        total_atrasados += atrasados_area
        if atrasados_area > max_atrasados_setor:
            max_atrasados_setor = atrasados_area
            setor_critico = area_en
        secoes += (
            '<div style="background:#111827;color:white;padding:8px 12px;'
            'border-radius:6px 6px 0 0;margin-top:24px;font-size:13px;">'
            f"<strong>{escape(area_en)}</strong> — {len(lista)} open"
            + (
                f' &nbsp;·&nbsp; <span style="color:#fca5a5;">{atrasados_area} overdue</span>'
                if atrasados_area
                else ""
            )
            + "</div>"
            + _tabela_html(lista, link_base)
        )

    cancelados = buscar_chamados_cancelados_semana()
    secao_cancelados = ""
    if cancelados:
        secao_cancelados = (
            '<div style="background:#dc2626;color:white;padding:8px 12px;'
            'border-radius:6px 6px 0 0;margin-top:24px;font-size:13px;">'
            f"<strong>Cancelled this week</strong> — {len(cancelados)}"
            "</div>" + _tabela_html(cancelados, link_base)
        )

    cards = _cards_resumo_html(
        len(chamados), total_atrasados, len(por_area), setor_critico, len(cancelados)
    )

    # /admin exige perfil supervisor/admin/admin_global (@requer_supervisor_area) —
    # um gerente_producao/assistente_gm/gm "puro" não tem acesso lá. O painel
    # gerencial (@requer_gestor_ou_admin) é a rota que eles realmente enxergam.
    link_gestor_dashboard = f"{link_base}/gestor/dashboard" if link_base else ""
    btn = (
        f'<a href="{link_gestor_dashboard}" style="background:#2563eb;color:white;padding:10px 20px;'
        f'text-decoration:none;border-radius:6px;display:inline-block;margin-top:20px;">Open dashboard</a>'
        if link_gestor_dashboard
        else ""
    )

    assunto = f"Weekly report — All sectors — {data_ref}"

    for nivel, email_gestor in mapa_niveis.items():
        usuario_gestor = Usuario.get_by_email(email_gestor)
        nome = getattr(usuario_gestor, "nome", None) or email_gestor
        label = NIVEL_LABEL_EN.get(nivel, "Manager")

        html = (
            '<div style="font-family:Arial,sans-serif;max-width:760px;">'
            '<div style="border-left:4px solid #2563eb;padding-left:12px;">'
            '<h2 style="color:#111827;margin:0;">Weekly Report — All Sectors</h2>'
            f'<p style="color:#6b7280;margin:4px 0 0;font-size:13px;">{data_ref}</p>'
            "</div>"
            f'<p style="margin-top:16px;">Hello, <strong>{escape(nome)}</strong> ({label}).</p>'
            f"{cards}"
            f"{secoes}{secao_cancelados}{btn}"
            '<p style="margin-top:24px;color:#9ca3af;font-size:11px;"><em>Andon</em></p>'
            "</div>"
        )

        ok, err = enviar_email(email_gestor, assunto, html, importance="low")
        if ok:
            logger.info(
                "Relatório semanal (todas as áreas) enviado para %s (%s)",
                nivel,
                email_gestor,
            )
        else:
            logger.warning(
                "Falha ao enviar relatório de todas as áreas para %s (%s): %s",
                nivel,
                email_gestor,
                err,
            )


def enviar_alertas_prazo_24h() -> dict[str, Any]:
    """
    Dispara alerta de prazo (24h) para responsáveis de chamados em risco.
    Critério: chamados com status Aberto/Em Atendimento cujo SLA está "Em risco".
    """
    chamados = buscar_chamados_abertos()
    elegiveis = [
        c
        for c in chamados
        if c.get("sla_label") == "Em risco" and not c.get("alerta_prazo_24h_enviado_em")
    ]

    enviados = ignorados = erros = 0

    for c in elegiveis:
        responsavel_id = c.get("responsavel_id")
        if not responsavel_id:
            ignorados += 1
            continue

        responsavel = Usuario.get_by_id(responsavel_id)
        email = (getattr(responsavel, "email", None) or "").strip() if responsavel else ""
        if not email:
            ignorados += 1
            continue

        try:
            notificar_responsavel_prazo_24h(
                chamado_id=c.get("id", ""),
                numero_chamado=c.get("numero", ""),
                responsavel_email=email,
                categoria=c.get("categoria", ""),
                tipo_solicitacao=c.get("tipo", ""),
                area=c.get("area", ""),
                solicitante_nome=c.get("solicitante", ""),
                descricao_resumo="",
            )
            chamado_id = c.get("id")
            if chamado_id:
                chamado_atual = Chamado.get_by_id(chamado_id)
                if chamado_atual is not None:
                    chamado_atual.atualizar_campos(
                        alerta_prazo_24h_enviado_em=datetime.now(ZoneInfo(Config.SLA_TIMEZONE))
                    )
                    Historico(
                        chamado_id=chamado_id,
                        usuario_id="sistema",
                        usuario_nome="Sistema (Alerta de Prazo 24h)",
                        acao="alerta_prazo_24h",
                        campo_alterado="alerta_prazo_24h_enviado_em",
                        valor_anterior=None,
                        valor_novo="Em risco",
                        detalhe=f"E-mail enviado para {email}",
                    ).save()
            enviados += 1
        except Exception as exc:
            erros += 1
            logger.exception(
                "Erro ao enviar alerta 24h para chamado %s: %s",
                c.get("numero", c.get("id", "sem_id")),
                exc,
            )

    logger.info(
        "Alerta 24h executado: elegiveis=%d enviados=%d ignorados=%d erros=%d",
        len(elegiveis),
        enviados,
        ignorados,
        erros,
    )
    return {
        "elegiveis": len(elegiveis),
        "enviados": enviados,
        "ignorados": ignorados,
        "erros": erros,
    }
