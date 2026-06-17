"""
Notification Service: E-mail via Microsoft Graph API (client credentials).

- Approver (responsible): notified when a new ticket is created.
- Requester: notified on status change (In Progress / Completed).
- Responsible: 24h deadline alert.
- Additional departments: supervisor notified when department is added.
- New user: receives credentials by e-mail on registration.

Required environment variables:
  GRAPH_TENANT_ID     — Azure AD Directory (tenant) ID
  GRAPH_CLIENT_ID     — Application (client) ID
  GRAPH_CLIENT_SECRET — Client secret value
  GRAPH_SENDER_EMAIL  — Sender mailbox (e.g. dtxls.support@dtx.aero)
"""

import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from html import escape

from flask import current_app, request

from app.services.email_templates import (
    build_cta_button,
    build_detail_table,
    build_email_shell,
    build_two_ctas,
)

logger = logging.getLogger(__name__)


def _config(key: str, default=None):
    """Read value from Flask config. Returns default if outside app context."""
    try:
        return current_app.config.get(key, default)
    except RuntimeError:
        return default


def _enviar_via_graph(
    destinatario: str,
    assunto: str,
    corpo_html: str,
    corpo_texto: str | None,
    from_addr: str,
) -> tuple:
    """Send e-mail via Microsoft Graph API (client credentials)."""
    import json

    tenant_id = os.getenv("GRAPH_TENANT_ID", "").strip()
    client_id = os.getenv("GRAPH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GRAPH_CLIENT_SECRET", "").strip()
    sender_email = os.getenv("GRAPH_SENDER_EMAIL", "").strip() or from_addr.strip()

    if not all([tenant_id, client_id, client_secret, sender_email]):
        return (
            False,
            "Incomplete configuration: set GRAPH_TENANT_ID, GRAPH_CLIENT_ID, "
            "GRAPH_CLIENT_SECRET and GRAPH_SENDER_EMAIL",
        )

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_data = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }
    ).encode("utf-8")

    try:
        req_token = urllib.request.Request(token_url, data=token_data, method="POST")
        with urllib.request.urlopen(req_token, timeout=10) as resp:  # nosec B310
            token_resp = json.loads(resp.read().decode("utf-8"))
            access_token = token_resp.get("access_token")
            if not access_token:
                err = f"Token not obtained: {list(token_resp.keys())}"
                logger.warning(err)
                return (False, err)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        err = f"Graph token HTTP {e.code}: {body}"
        logger.warning("Failed to obtain Graph token: %s", err)
        return (False, err)
    except Exception as e:
        logger.exception("Failed to obtain Graph token for %s: %s", destinatario, e)
        return (False, f"OAuth2 token failure: {e}")

    payload = json.dumps(
        {
            "message": {
                "subject": assunto,
                "body": {"contentType": "HTML", "content": corpo_html},
                "toRecipients": [{"emailAddress": {"address": destinatario}}],
            },
            "saveToSentItems": False,
        }
    ).encode("utf-8")

    send_url = f"https://graph.microsoft.com/v1.0/users/{urllib.parse.quote(sender_email)}/sendMail"
    req_send = urllib.request.Request(
        send_url,
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req_send, timeout=15) as resp:  # nosec B310
            if resp.status == 202:
                logger.info("E-mail sent via Graph to %s: %s", destinatario, assunto[:60])
                return (True, None)
            err = f"Graph sendMail unexpected status: {resp.status}"
            logger.warning(err)
            return (False, err)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        err = f"Graph sendMail HTTP {e.code}: {body}"
        logger.warning("Graph sendMail failed for %s: %s", destinatario, err)
        return (False, err)
    except Exception as e:
        logger.exception("Failed to send via Graph to %s: %s", destinatario, e)
        return (False, str(e))


def enviar_email(destinatario: str, assunto: str, corpo_html: str, corpo_texto: str = None):
    """Send e-mail via Microsoft Graph API. Returns (True, None) or (False, error)."""
    if not destinatario or not destinatario.strip():
        logger.warning("Notification skipped: empty recipient")
        return (False, None)
    from_addr = os.getenv("GRAPH_SENDER_EMAIL", "").strip() or "noreply@localhost"
    return _enviar_via_graph(destinatario.strip(), assunto, corpo_html, corpo_texto, from_addr)


def _base_url() -> str:
    base = (_config("APP_BASE_URL") or os.getenv("APP_BASE_URL") or "").strip()
    if not base:
        try:
            if request and getattr(request, "url_root", None):
                base = request.url_root.rstrip("/")
        except RuntimeError:
            pass
    return base.rstrip("/") if base else ""


def _link_chamado(chamado_id: str) -> str:
    base = _base_url()
    return f"{base}/chamado/{chamado_id}/historico" if base else ""


def _link_dashboard() -> str:
    base = _base_url()
    return f"{base}/admin" if base else ""


# ---------------------------------------------------------------------------
# New ticket — notify responsible (supervisor)
# ---------------------------------------------------------------------------


def notificar_aprovador_novo_chamado(
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    tipo_solicitacao: str,
    descricao_resumo: str,
    area: str,
    solicitante_nome: str,
    responsavel_usuario,
    solicitante_email: str = None,
) -> None:
    """Notify the responsible that a new ticket has been assigned to them."""
    if not responsavel_usuario or not getattr(responsavel_usuario, "email", None):
        logger.debug("Approver has no e-mail; notification not sent")
        return

    email_dest = responsavel_usuario.email.strip()
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    resumo_truncado = descricao_resumo[:500] + ("..." if len(descricao_resumo) > 500 else "")
    solicitante_linha = solicitante_nome
    if solicitante_email and solicitante_email.strip():
        solicitante_linha += f" ({solicitante_email.strip()})"

    assunto = f"New ticket assigned: {numero_chamado}"

    detalhes_html = build_detail_table(
        [
            ("Number", numero_chamado),
            ("Category", categoria),
            ("Type", tipo_solicitacao),
            ("Area", area),
            ("Requester", solicitante_linha),
        ]
    )
    summary_html = f'<p style="margin: 12px 0;">{escape(resumo_truncado)}</p>'

    ctas = []
    if link:
        ctas.append(("View ticket history", link, "#2563eb"))
    if link_dash:
        ctas.append(("View sector tickets", link_dash, "#6b7280"))
    botoes_html = build_two_ctas(ctas) if ctas else ""

    corpo_html = build_email_shell(
        header_title="New ticket assigned",
        header_color="#2563eb",
        body_html=(
            "<p>Hello, a new ticket has been assigned to you.</p>"
            + detalhes_html
            + summary_html
            + botoes_html
        ),
    )
    corpo_texto = (
        f"Number: {numero_chamado}\n"
        f"Category: {categoria}\nType: {tipo_solicitacao}\n"
        f"Area: {area}\nRequester: {solicitante_linha}\n"
        f"Summary: {resumo_truncado}"
    )

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info("New ticket notification sent to %s", email_dest)
    else:
        logger.warning("Failed to notify approver %s: %s", email_dest, err)


# ---------------------------------------------------------------------------
# 24h deadline alert — notify responsible
# ---------------------------------------------------------------------------


def notificar_responsavel_prazo_24h(
    chamado_id: str,
    numero_chamado: str,
    responsavel_email: str,
    categoria: str = "",
    tipo_solicitacao: str = "",
    area: str = "",
    solicitante_nome: str = "",
    descricao_resumo: str = "",
) -> None:
    """Warn the responsible that the ticket is about to breach its SLA (24h)."""
    if not responsavel_email or not str(responsavel_email).strip():
        logger.warning("24h alert skipped for %s: responsible has no e-mail", numero_chamado)
        return

    email_dest = responsavel_email.strip()
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    resumo_truncado = (descricao_resumo or "")[:500] + (
        "..." if len(descricao_resumo or "") > 500 else ""
    )
    assunto = f"Ticket {numero_chamado}: deadline in 24h"

    detalhes_html = build_detail_table(
        [
            ("Number", numero_chamado),
            ("Category", categoria),
            ("Type", tipo_solicitacao),
            ("Area", area),
            ("Requester", solicitante_nome),
        ]
    )
    summary_html = (
        f'<p style="margin: 12px 0;">{escape(resumo_truncado)}</p>' if resumo_truncado else ""
    )

    ctas = []
    if link:
        ctas.append(("View ticket history", link, "#d97706"))
    if link_dash:
        ctas.append(("View sector tickets", link_dash, "#6b7280"))
    botoes_html = build_two_ctas(ctas) if ctas else ""

    corpo_html = build_email_shell(
        header_title="Ticket nearing deadline (24h)",
        header_color="#d97706",
        body_html=(
            "<p>Hello, this ticket is approaching its SLA deadline (24h remaining).</p>"
            + detalhes_html
            + summary_html
            + botoes_html
        ),
    )
    corpo_texto = (
        f"Number: {numero_chamado}\n"
        "Warning: this ticket is about to breach its SLA (24h remaining).\n"
        f"Category: {categoria}\nType: {tipo_solicitacao}\n"
        f"Area: {area}\nRequester: {solicitante_nome}"
    )

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info("24h alert sent to %s (ticket %s)", email_dest, numero_chamado)
    else:
        logger.warning("Failed to send 24h alert to %s: %s", email_dest, err)


# ---------------------------------------------------------------------------
# New user registered — send credentials
# ---------------------------------------------------------------------------


def notificar_novo_usuario_cadastrado(
    usuario_id: str,
    usuario_email: str,
    usuario_nome: str = "",
    perfil: str = "",
    areas: list | None = None,
    senha_inicial: str = "",
) -> None:
    """Send a welcome e-mail with credentials to a newly registered user."""
    if not usuario_email or not str(usuario_email).strip():
        logger.warning("New user notification skipped: empty e-mail")
        return

    email_dest = usuario_email.strip()
    areas_str = ", ".join(areas or [])
    link_dash = _link_dashboard()
    assunto = "Welcome to DTX Digital Andon — your access credentials"

    detalhes_html = build_detail_table(
        [
            ("Role", perfil or "N/A"),
            ("Areas", areas_str or "N/A"),
            ("E-mail", email_dest),
            ("Initial password", senha_inicial),
        ]
    )
    acesso_html = (
        f'<p style="margin-top: 20px;">{build_cta_button("Open system", link_dash, "#2563eb")}</p>'
        if link_dash
        else ""
    )

    corpo_html = build_email_shell(
        header_title="New account — DTX Digital Andon",
        header_color="#2563eb",
        body_html=(
            f"<p>Hello, <strong>{escape(usuario_nome or 'user')}</strong>! "
            "An account has been created for you in DTX Digital Andon.</p>"
            + detalhes_html
            + "<p>You will be asked to change your password on first login.</p>"
            + "<p>If you do not recognize this account, contact support immediately.</p>"
            + acesso_html
        ),
    )
    corpo_texto = (
        f"Hello {usuario_nome or 'user'},\n\n"
        "An account has been created for you in DTX Digital Andon.\n"
        f"Role: {perfil}\nAreas: {areas_str or 'N/A'}\n"
        f"E-mail: {email_dest}\nInitial password: {senha_inicial}\n\n"
        "You will be asked to change your password on first login.\n"
        "If you do not recognize this account, contact support immediately."
    )

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info("Registration e-mail sent to %s", email_dest)
    else:
        logger.warning("Failed to send registration e-mail to %s: %s", email_dest, err)


# ---------------------------------------------------------------------------
# Additional department included in ticket — notify department supervisor
# ---------------------------------------------------------------------------


def notificar_responsavel_setor_adicional(
    chamado_id: str,
    numero_chamado: str,
    email_responsavel_setor: str,
    setor_adicional: str,
    categoria: str = "",
    tipo_solicitacao: str = "",
    solicitante_nome: str = "",
    quem_adicionou_nome: str = "",
    descricao_resumo: str = "",
) -> None:
    """Notify the responsible of an additional department included in the ticket."""
    if not email_responsavel_setor or not str(email_responsavel_setor).strip():
        logger.warning("Additional dept notification skipped for %s: empty e-mail", numero_chamado)
        return

    email_dest = email_responsavel_setor.strip()
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    resumo_truncado = (descricao_resumo or "")[:500] + (
        "..." if len(descricao_resumo or "") > 500 else ""
    )
    assunto = f"Ticket {numero_chamado}: your department has been included"

    detalhes_html = build_detail_table(
        [
            ("Number", numero_chamado),
            ("Department", setor_adicional),
            ("Added by", quem_adicionou_nome),
            ("Category", categoria),
            ("Type", tipo_solicitacao),
            ("Requester", solicitante_nome),
        ]
    )
    summary_html = (
        f'<p style="margin: 12px 0;">{escape(resumo_truncado)}</p>' if resumo_truncado else ""
    )

    ctas = []
    if link:
        ctas.append(("View ticket history", link, "#2563eb"))
    if link_dash:
        ctas.append(("View sector tickets", link_dash, "#6b7280"))
    botoes_html = build_two_ctas(ctas) if ctas else ""

    corpo_html = build_email_shell(
        header_title="Your department has been included in a ticket",
        header_color="#2563eb",
        body_html=(
            "<p>Hello, your department has been included in this ticket.</p>"
            + detalhes_html
            + summary_html
            + botoes_html
        ),
    )
    corpo_texto = (
        f"Number: {numero_chamado}\nDepartment: {setor_adicional}\n"
        f"Added by: {quem_adicionou_nome}\nCategory: {categoria}\n"
        f"Type: {tipo_solicitacao}\nRequester: {solicitante_nome}"
    )

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info(
            "Additional dept notification sent to %s (ticket %s)", email_dest, numero_chamado
        )
    else:
        logger.warning("Failed to notify additional dept %s: %s", email_dest, err)


def notificar_setores_adicionais_chamado(
    chamado_id: str,
    numero_chamado: str,
    setores_novos: list,
    categoria: str,
    tipo_solicitacao: str,
    descricao_resumo: str,
    solicitante_nome: str,
    quem_adicionou_nome: str,
    setores_nomes: str = None,
) -> None:
    """Notify all supervisors of departments added to the ticket."""
    if not setores_novos:
        return

    from app.models_usuario import Usuario
    from app.utils_areas import setor_para_area

    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    setores_str = setores_nomes or ", ".join(setores_novos)
    resumo_truncado = (descricao_resumo or "")[:500] + (
        "..." if len(descricao_resumo or "") > 500 else ""
    )

    usuarios_unicos: dict = {}
    for setor in setores_novos:
        areas_busca = [setor]
        area_norm = setor_para_area(setor)
        if area_norm and area_norm != setor:
            areas_busca.append(area_norm)
        for area in areas_busca:
            for u in Usuario.get_supervisores_por_area(area):
                if u and u.id and u.id not in usuarios_unicos:
                    usuarios_unicos[u.id] = u

    for usuario in usuarios_unicos.values():
        email = getattr(usuario, "email", None)
        if not email or not str(email).strip():
            continue

        assunto = f"Ticket {numero_chamado}: your department has been included"
        detalhes_html = build_detail_table(
            [
                ("Number", numero_chamado),
                ("Category", categoria),
                ("Type", tipo_solicitacao),
                ("Requester", solicitante_nome),
                ("Added by", quem_adicionou_nome),
                ("Departments added", setores_str),
            ]
        )
        summary_html = (
            f'<p style="margin: 12px 0;">{escape(resumo_truncado)}</p>' if resumo_truncado else ""
        )

        ctas = []
        if link:
            ctas.append(("View ticket history", link, "#2563eb"))
        if link_dash:
            ctas.append(("View sector tickets", link_dash, "#6b7280"))
        botoes_html = build_two_ctas(ctas) if ctas else ""

        corpo_html = build_email_shell(
            header_title="Ticket: your department has been included",
            header_color="#2563eb",
            body_html=(
                f"<p>Hello, ticket <strong>{escape(numero_chamado)}</strong> "
                f"included your department, added by <strong>{escape(quem_adicionou_nome)}</strong>.</p>"
                + detalhes_html
                + summary_html
                + botoes_html
            ),
        )
        corpo_texto = (
            f"Number: {numero_chamado}\nRequester: {solicitante_nome}\n"
            f"Added by: {quem_adicionou_nome}\nDepartments: {setores_str}"
        )

        ok, err = enviar_email(email.strip(), assunto, corpo_html, corpo_texto)
        if ok:
            logger.info("Dept added notification sent to %s (ticket %s)", email, numero_chamado)
        else:
            logger.warning("Failed to notify dept added to %s: %s", email, err)


# ---------------------------------------------------------------------------
# Status change — notify requester
# ---------------------------------------------------------------------------


def notificar_solicitante_status(
    chamado_id: str,
    numero_chamado: str,
    novo_status: str,
    categoria: str,
    solicitante_usuario,
) -> None:
    """Notify the requester about a status change (In Progress / Completed)."""
    if not solicitante_usuario:
        return

    email = (getattr(solicitante_usuario, "email", None) or "").strip()
    if not email:
        return

    nome = getattr(solicitante_usuario, "nome", None) or "Requester"
    link = _link_chamado(chamado_id)

    if novo_status == "Concluído":
        assunto = f"Ticket {numero_chamado}: completed"
        header_title = f"Ticket {numero_chamado}: Completed"
        header_color = "#059669"
        msg_status = "your ticket has been <strong>completed</strong>"
    else:
        assunto = f"Ticket {numero_chamado}: in progress"
        header_title = f"Ticket {numero_chamado}: In Progress"
        header_color = "#2563eb"
        msg_status = "your ticket is <strong>in progress</strong>"

    detalhes_html = build_detail_table(
        [("Ticket", numero_chamado), ("Category", categoria), ("Status", novo_status)]
    )
    botoes_html = (
        f'<p style="margin-top:20px;">{build_cta_button("View ticket", link, "#2563eb")}</p>'
        if link
        else '<p style="color:#6b7280;">Log in to the system to track your ticket.</p>'
    )

    corpo_html = build_email_shell(
        header_title=header_title,
        header_color=header_color,
        body_html=(
            f"<p>Hello, <strong>{escape(nome)}</strong>! We are letting you know that {msg_status}.</p>"
            + detalhes_html
            + botoes_html
        ),
    )
    corpo_texto = (
        f"Hello, {nome}!\n\n"
        f"Ticket: {numero_chamado}\nCategory: {categoria}\nStatus: {novo_status}"
        + (f"\n\nView ticket: {link}" if link else "")
    )

    ok, err = enviar_email(email, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info("Status e-mail (%s) sent to %s (ticket %s)", novo_status, email, numero_chamado)
    else:
        logger.warning("Failed to send status e-mail to %s: %s", email, err)
