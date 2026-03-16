"""
Serviço de Relatórios Semanais.

Toda sexta-feira às 10h (BRT) o APScheduler chama `enviar_relatorio_semanal()`.
A função busca chamados abertos/atrasados e envia e-mails para a caixa relay
(NOTIFY_RELAY_EMAIL) com assunto estruturado:

  REPORT_SEMANAL|{data}|{email_supervisor}
  REPORT_SEMANAL_ADMIN|{data}|{email_admin}

O Power Automate já observa essa caixa. Basta adicionar uma condição para
tratar subjects que começam com "REPORT_SEMANAL" e encaminhar o corpo HTML
ao endereço extraído do subject (3º segmento após "|").
"""

import logging
import os
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import pytz

from app.database import db
from app.models import Chamado
from app.models_usuario import Usuario
from app.services.analytics import _to_datetime, obter_sla_para_exibicao
from app.services.notifications import _base_url, _link_dashboard, enviar_email

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


def _relay_email() -> str:
    """Retorna o e-mail relay (mesmo usado nas notificações de novo chamado)."""
    try:
        from flask import current_app
        val = current_app.config.get("NOTIFY_RELAY_EMAIL")
        if val:
            return val.strip()
    except RuntimeError:
        pass
    return (os.getenv("NOTIFY_RELAY_EMAIL") or "dtxls.support@dtx.aero").strip()


# ---------------------------------------------------------------------------
# Busca de chamados
# ---------------------------------------------------------------------------

def buscar_chamados_abertos() -> list[dict[str, Any]]:
    """
    Retorna todos os chamados Abertos / Em Atendimento enriquecidos com SLA.
    """
    resultado: list[dict[str, Any]] = []
    for status in ("Aberto", "Em Atendimento"):
        try:
            docs = (
                db.collection("chamados")
                .where("status", "==", status)
                .limit(MAX_DOCS)
                .stream()
            )
            for doc in docs:
                data = doc.to_dict()
                if not data:
                    continue
                chamado = Chamado.from_dict(data, doc.id)
                sla_info = obter_sla_para_exibicao(chamado) or {}
                resultado.append({
                    "id": doc.id,
                    "numero": chamado.numero_chamado or doc.id,
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
                })
        except Exception as exc:
            logger.exception("Erro ao buscar chamados status=%s: %s", status, exc)
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
        dias_txt = f' ({c.get("sla_dias")}d)' if c.get("sla_dias") else ''
        badge = f'<span style="color:{cor_sla};font-weight:600;">{c["sla_label"] or c["status"]}{dias_txt}</span>'
        link = f"{link_base}/chamado/{c['id']}/historico" if link_base else ""
        numero_html = (
            f'<a href="{link}" style="color:#2563eb;text-decoration:none;">{c["numero"]}</a>'
            if link else c["numero"]
        )
        linhas.append(
            "<tr>"
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;">{numero_html}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;">{c["categoria"]}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;">{c["tipo"]}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;">{c["solicitante"]}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;">{c["data_abertura_fmt"]}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;">{c["dias_aberto"]}d</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;">{badge}</td>'
            "</tr>"
        )
    return (
        '<table style="width:100%;border-collapse:collapse;">'
        f"{cabecalho}{''.join(linhas)}"
        "</table>"
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
        if link_dash else ""
    )

    html = (
        '<div style="font-family:Arial,sans-serif;max-width:760px;">'
        f'<h2 style="color:#111827;">Weekly Report — {data_ref}</h2>'
        f'<p>Hello, <strong>{nome}</strong>.</p>'
        f'<p><strong>Total:</strong> {len(chamados)} &nbsp;|&nbsp; '
        f'<span style="color:#dc2626;">Overdue: {len(atrasados)}</span> &nbsp;|&nbsp; '
        f'Others: {len(outros)}</p>'
        f'{secoes}{btn}'
        '<p style="margin-top:24px;color:#9ca3af;font-size:11px;"><em>Ticket System — DTX</em></p>'
        '</div>'
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
            linhas.append(f"  {c['numero']} | {c['categoria']} | {c['solicitante']} | {c['data_abertura_fmt']} ({c['dias_aberto']}d)")
    if outros:
        linhas.append("== OPEN / IN PROGRESS ==")
        for c in outros:
            linhas.append(f"  {c['numero']} | {c['categoria']} | {c['solicitante']} | {c['data_abertura_fmt']} ({c['dias_aberto']}d)")

    return html, "\n".join(linhas)


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def enviar_relatorio_semanal() -> dict[str, Any]:
    """
    Busca chamados abertos/atrasados e envia para o relay um e-mail por supervisor:

      Subject: REPORT_SEMANAL|{data}|{email_supervisor}

    O Power Automate lê o subject, extrai o e-mail (3º segmento) e encaminha
    o corpo HTML ao supervisor — mesmo mecanismo do CHAMADO_NOVO.

    Admins recebem um resumo consolidado com subject:
      REPORT_SEMANAL_ADMIN|{data}|{email_admin}

    Retorna dict: enviados, ignorados, erros, total_chamados, total_atrasados.
    """
    data_ref = _agora_brasilia().strftime("%d/%m/%Y")
    link_base = _base_url()
    link_dash = _link_dashboard()
    relay = _relay_email()

    chamados = buscar_chamados_abertos()
    total_chamados = len(chamados)
    total_atrasados = sum(1 for c in chamados if c["atrasado"])

    logger.info(
        "Relatório semanal: %d abertos, %d atrasados — relay: %s",
        total_chamados, total_atrasados, relay,
    )

    if not chamados:
        logger.info("Nenhum chamado aberto; relatório semanal não enviado.")
        return {"enviados": 0, "ignorados": 0, "erros": 0,
                "total_chamados": 0, "total_atrasados": 0}

    grupos: dict[str, list] = defaultdict(list)
    for c in chamados:
        grupos[c["responsavel_id"]].append(c)

    enviados = ignorados = erros = 0

    for responsavel_id, lista in grupos.items():
        if not responsavel_id:
            ignorados += len(lista)
            continue

        supervisor = Usuario.get_by_id(responsavel_id)
        if not supervisor or not getattr(supervisor, "email", None):
            logger.debug("Supervisor %s sem e-mail; ignorado.", responsavel_id)
            ignorados += len(lista)
            continue

        email_sup = supervisor.email.strip()
        nome = supervisor.nome or email_sup
        # Assunto estruturado: Power Automate extrai email_sup do 3º segmento
        assunto = f"REPORT_SEMANAL|{data_ref}|{email_sup}"

        html, texto = _corpo_supervisor(nome, lista, link_dash, link_base, data_ref)
        ok, err = enviar_email(relay, assunto, html, texto)
        if ok:
            enviados += 1
            logger.info("Relatório semanal (relay) enviado para supervisor %s (%d chamados)", email_sup, len(lista))
        else:
            erros += 1
            logger.warning("Falha ao enviar relatório (relay) para supervisor %s: %s", email_sup, err)

    _enviar_resumo_admins(chamados, grupos, data_ref, link_dash, link_base, relay)

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
    data_ref: str,
    link_dash: str,
    link_base: str,
    relay: str,
) -> None:
    """Envia resumo consolidado para cada admin via relay."""
    try:
        admins = [
            u for u in Usuario.get_all()
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
        sup = Usuario.get_by_id(resp_id) if resp_id else None
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
        "</tr>"
        + "".join(linhas_sup)
        + "</table>"
    )

    btn = (
        f'<a href="{link_dash}" style="background:#2563eb;color:white;padding:10px 20px;'
        f'text-decoration:none;border-radius:6px;display:inline-block;margin-top:20px;">Open dashboard</a>'
        if link_dash else ""
    )

    html_admin = (
        '<div style="font-family:Arial,sans-serif;max-width:760px;">'
        f'<h2 style="color:#111827;">Weekly Summary — {data_ref}</h2>'
        f'<p><strong>Total open:</strong> {len(chamados)} &nbsp;|&nbsp; '
        f'<span style="color:#dc2626;"><strong>Overdue:</strong> {len(atrasados)}</span></p>'
        '<h3 style="margin-top:20px;">By assignee</h3>'
        f'{tabela_sup}'
        f'<h3 style="color:#dc2626;margin-top:24px;">Overdue tickets ({len(atrasados)})</h3>'
        + (_tabela_html(atrasados, link_base) if atrasados else '<p style="color:#6b7280;">None.</p>')
        + f'{btn}'
        '<p style="margin-top:24px;color:#9ca3af;font-size:11px;"><em>Ticket System — DTX</em></p>'
        '</div>'
    )

    for admin in admins:
        email_admin = admin.email.strip()
        assunto = f"REPORT_SEMANAL_ADMIN|{data_ref}|{email_admin}"
        ok, err = enviar_email(relay, assunto, html_admin)
        if ok:
            logger.info("Resumo semanal (relay) enviado para admin %s", email_admin)
        else:
            logger.warning("Falha ao enviar resumo (relay) para admin %s: %s", email_admin, err)
