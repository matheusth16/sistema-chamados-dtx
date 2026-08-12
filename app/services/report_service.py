"""
Serviço de Relatórios Semanais.

Toda sexta-feira às 10h (BRT) o APScheduler chama `enviar_relatorio_semanal()`.
A função busca chamados abertos/atrasados e envia e-mails diretamente para
cada supervisor e admin via Microsoft Graph API.
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

import pytz
from sqlalchemy import select

from app import db as db_module
from app.db.models.chamado import ChamadoRow
from app.i18n import get_translated_status
from app.models import Chamado
from app.models_historico import Historico
from app.models_usuario import Usuario
from app.services.analytics import _to_datetime, obter_sla_para_exibicao
from app.services.gestor_escalonamento_service import construir_mapa_gestor_setor
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
                "categoria": chamado.categoria or "—",
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
        "<th style='padding:8px 10px;text-align:left;font-size:12px;'>Requester</th>"
        "<th style='padding:8px 10px;text-align:left;font-size:12px;'>Opened</th>"
        "<th style='padding:8px 10px;text-align:left;font-size:12px;'>Days</th>"
        "<th style='padding:8px 10px;text-align:left;font-size:12px;'>SLA</th>"
        "</tr>"
    )
    linhas = []
    for c in chamados:
        if c["atrasado"]:
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
    """Envia resumo consolidado para cada admin diretamente."""
    try:
        admins = [
            u
            for u in Usuario.get_all()
            if getattr(u, "perfil", "") == "admin" and getattr(u, "email", None)
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

        atrasados = [c for c in lista if c["atrasado"]]
        html = (
            '<div style="font-family:Arial,sans-serif;max-width:760px;">'
            f'<h2 style="color:#111827;">Weekly Area Report — {escape(area)} — {data_ref}</h2>'
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
        assunto = f"Weekly area report — {area} — {data_ref}"
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
