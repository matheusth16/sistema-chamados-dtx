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

from app.i18n import (
    get_translated_category,
    get_translated_role,
    get_translated_sector,
    get_translated_sector_list,
    get_translated_status,
)
from app.services.email_templates import (
    build_cta_button,
    build_detail_table,
    build_email_shell,
    build_two_ctas,
)

_EMAIL_LANG = "en"


def _tc(v: str) -> str:
    return get_translated_category(v, _EMAIL_LANG) if v else ""


def _ts(v: str) -> str:
    return get_translated_sector(v, _EMAIL_LANG) if v else ""


def _tsl(v: str) -> str:
    return get_translated_sector_list(v, _EMAIL_LANG) if v else ""


def _tst(v: str) -> str:
    return get_translated_status(v, _EMAIL_LANG) if v else ""


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


def _email_envio_permitido() -> bool:
    """True quando o ambiente permite envio real (produção ou opt-in explícito)."""
    if _config("TESTING"):
        return False
    return bool(_config("NOTIFY_EMAIL_ENABLED", False))


def enviar_email(destinatario: str, assunto: str, corpo_html: str, corpo_texto: str = None):
    """Send e-mail via Microsoft Graph API. Returns (True, None) or (False, error)."""
    if not destinatario or not destinatario.strip():
        logger.warning("Notification skipped: empty recipient")
        return (False, None)
    if not _email_envio_permitido():
        motivo = "TESTING" if _config("TESTING") else "NOTIFY_EMAIL_ENABLED=false"
        logger.info(
            "E-mail suppressed (%s): %s — %s",
            motivo,
            destinatario.strip(),
            assunto[:80],
        )
        return (True, None)
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
    cat_d = _tc(categoria)
    tipo_d = _ts(tipo_solicitacao)
    area_d = _ts(area)

    assunto = f"New ticket assigned: {numero_chamado}"

    detalhes_html = build_detail_table(
        [
            ("Number", numero_chamado),
            ("Category", cat_d),
            ("Type", tipo_d),
            ("Area", area_d),
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
        f"Category: {cat_d}\nType: {tipo_d}\n"
        f"Area: {area_d}\nRequester: {solicitante_linha}\n"
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
    cat_d = _tc(categoria)
    tipo_d = _ts(tipo_solicitacao)
    area_d = _ts(area)
    assunto = f"Ticket {numero_chamado}: deadline in 24h"

    detalhes_html = build_detail_table(
        [
            ("Number", numero_chamado),
            ("Category", cat_d),
            ("Type", tipo_d),
            ("Area", area_d),
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
        f"Category: {cat_d}\nType: {tipo_d}\n"
        f"Area: {area_d}\nRequester: {solicitante_nome}"
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
    perfil_display = get_translated_role(perfil, "en") if perfil else "N/A"
    areas_display = get_translated_sector_list(", ".join(areas or []), "en") or "N/A"
    link_dash = _link_dashboard()
    assunto = "Welcome to DTX Service Portal — your access credentials"

    detalhes_html = build_detail_table(
        [
            ("Role", perfil_display),
            ("Areas", areas_display),
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
        header_title="New account — DTX Service Portal",
        header_color="#2563eb",
        body_html=(
            f"<p>Hello, <strong>{escape(usuario_nome or 'user')}</strong>! "
            "An account has been created for you in DTX Service Portal.</p>"
            + detalhes_html
            + "<p>You will be asked to change your password on first login.</p>"
            + "<p>If you do not recognize this account, contact support immediately.</p>"
            + acesso_html
        ),
    )
    corpo_texto = (
        f"Hello {usuario_nome or 'user'},\n\n"
        "An account has been created for you in DTX Service Portal.\n"
        f"Role: {perfil_display}\nAreas: {areas_display}\n"
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
    setor_d = _ts(setor_adicional)
    cat_d = _tc(categoria)
    tipo_d = _ts(tipo_solicitacao)
    assunto = f"Ticket {numero_chamado}: your department has been included"

    detalhes_html = build_detail_table(
        [
            ("Number", numero_chamado),
            ("Department", setor_d),
            ("Added by", quem_adicionou_nome),
            ("Category", cat_d),
            ("Type", tipo_d),
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
        f"Number: {numero_chamado}\nDepartment: {setor_d}\n"
        f"Added by: {quem_adicionou_nome}\nCategory: {cat_d}\n"
        f"Type: {tipo_d}\nRequester: {solicitante_nome}"
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
    setores_str_d = _tsl(setores_str)
    cat_d = _tc(categoria)
    tipo_d = _ts(tipo_solicitacao)
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
                ("Category", cat_d),
                ("Type", tipo_d),
                ("Requester", solicitante_nome),
                ("Added by", quem_adicionou_nome),
                ("Departments added", setores_str_d),
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
            f"Added by: {quem_adicionou_nome}\nDepartments: {setores_str_d}"
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
    status_display = _tst(novo_status)
    cat_d = _tc(categoria)

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
        [("Ticket", numero_chamado), ("Category", cat_d), ("Status", status_display)]
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
        f"Ticket: {numero_chamado}\nCategory: {cat_d}\nStatus: {status_display}"
        + (f"\n\nView ticket: {link}" if link else "")
    )

    ok, err = enviar_email(email, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info("Status e-mail (%s) sent to %s (ticket %s)", novo_status, email, numero_chamado)
    else:
        logger.warning("Failed to send status e-mail to %s: %s", email, err)


# ---------------------------------------------------------------------------
# Ticket completed — ask requester to confirm resolution
# ---------------------------------------------------------------------------


def notificar_solicitante_confirmacao_pendente(
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    solicitante_usuario,
) -> None:
    """Notify the requester that the ticket is complete and awaits their confirmation."""
    if not solicitante_usuario:
        return
    email = (getattr(solicitante_usuario, "email", None) or "").strip()
    if not email:
        return

    nome = getattr(solicitante_usuario, "nome", None) or "Requester"
    link = _link_chamado(chamado_id)
    cat_d = _tc(categoria)

    assunto = f"Ticket {numero_chamado}: please confirm resolution"

    detalhes_html = build_detail_table(
        [("Ticket", numero_chamado), ("Category", cat_d), ("Status", "Completed")]
    )
    botoes_html = (
        f'<p style="margin-top:20px;">{build_cta_button("Confirm or reopen", link, "#059669")}</p>'
        if link
        else '<p style="color:#6b7280;">Log in to the system to confirm or reopen your ticket.</p>'
    )

    corpo_html = build_email_shell(
        header_title=f"Ticket {numero_chamado}: awaiting your confirmation",
        header_color="#059669",
        body_html=(
            f"<p>Hello, <strong>{escape(nome)}</strong>! "
            "Your ticket has been marked as <strong>completed</strong>. "
            "Please open it to confirm whether the issue was resolved — "
            "or reopen it if something is still pending.</p>" + detalhes_html + botoes_html
        ),
    )
    corpo_texto = (
        f"Hello, {nome}!\n\n"
        f"Ticket: {numero_chamado}\nCategory: {cat_d}\nStatus: Completed\n\n"
        "Please confirm whether the issue was resolved or reopen it."
        + (f"\n\nOpen ticket: {link}" if link else "")
    )

    ok, err = enviar_email(email, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info("Confirmation request sent to %s (ticket %s)", email, numero_chamado)
    else:
        logger.warning("Failed to send confirmation request to %s: %s", email, err)


# ---------------------------------------------------------------------------
# Ticket reopened by requester — notify responsible (supervisor)
# ---------------------------------------------------------------------------


def notificar_supervisor_chamado_reaberto(
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    motivo: str,
    solicitante_nome: str,
    responsavel_usuario,
) -> None:
    """Notify the responsible that the requester rejected the resolution and reopened the ticket."""
    if not responsavel_usuario:
        return
    email = (getattr(responsavel_usuario, "email", None) or "").strip()
    if not email:
        return

    nome_responsavel = getattr(responsavel_usuario, "nome", None) or "Responsible"
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    motivo_truncado = (motivo or "")[:500]
    cat_d = _tc(categoria)

    assunto = f"Ticket {numero_chamado}: reopened by requester"

    detalhes_html = build_detail_table(
        [
            ("Ticket", numero_chamado),
            ("Category", cat_d),
            ("Requester", solicitante_nome),
            ("Reason for reopening", motivo_truncado),
        ]
    )

    ctas = []
    if link:
        ctas.append(("View ticket history", link, "#dc2626"))
    if link_dash:
        ctas.append(("View sector tickets", link_dash, "#6b7280"))
    botoes_html = build_two_ctas(ctas) if ctas else ""

    corpo_html = build_email_shell(
        header_title=f"Ticket {numero_chamado}: reopened",
        header_color="#dc2626",
        body_html=(
            f"<p>Hello, <strong>{escape(nome_responsavel)}</strong>! "
            f"Ticket <strong>{escape(numero_chamado)}</strong> was <strong>reopened</strong> "
            f"by the requester <strong>{escape(solicitante_nome)}</strong>.</p>"
            + detalhes_html
            + botoes_html
        ),
    )
    corpo_texto = (
        f"Hello, {nome_responsavel}!\n\n"
        f"Ticket {numero_chamado} was reopened by {solicitante_nome}.\n"
        f"Category: {cat_d}\nReason: {motivo_truncado}"
        + (f"\n\nView ticket: {link}" if link else "")
    )

    ok, err = enviar_email(email, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info("Reopen notification sent to %s (ticket %s)", email, numero_chamado)
    else:
        logger.warning("Failed to send reopen notification to %s: %s", email, err)


# ---------------------------------------------------------------------------
# Escalonamento — Fase 3
# ---------------------------------------------------------------------------


def notificar_supervisor_transferencia_area(
    chamado_id: str,
    numero_chamado: str,
    area: str,
    categoria: str,
    motivo: str,
    responsavel_usuario,
) -> None:
    """Notifica o novo responsável que o chamado foi transferido para sua área."""
    if not responsavel_usuario or not getattr(responsavel_usuario, "email", None):
        logger.debug("Transfer notification skipped: recipient has no e-mail")
        return

    email_dest = responsavel_usuario.email.strip()
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    motivo_truncado = (motivo or "")[:500] + ("..." if len(motivo or "") > 500 else "")
    cat_d = _tc(categoria)
    area_d = _ts(area)

    assunto = f"Ticket transferred to your area: {numero_chamado}"

    detalhes_html = build_detail_table(
        [
            ("Number", numero_chamado),
            ("Category", cat_d),
            ("Area", area_d),
            ("Reason", motivo_truncado),
        ]
    )

    ctas = []
    if link:
        ctas.append(("View ticket", link, "#2563eb"))
    if link_dash:
        ctas.append(("View sector tickets", link_dash, "#6b7280"))
    botoes_html = build_two_ctas(ctas) if ctas else ""

    corpo_html = build_email_shell(
        header_title="Ticket transferred to your area",
        header_color="#2563eb",
        body_html=(
            f"<p>Hello, a ticket has been transferred to your area <strong>{escape(area_d)}</strong> "
            f"and assigned to you.</p>" + detalhes_html + botoes_html
        ),
    )
    corpo_texto = (
        f"Number: {numero_chamado}\n"
        f"Category: {cat_d}\nArea: {area_d}\n"
        f"Reason: {motivo_truncado}" + (f"\n\nView ticket: {link}" if link else "")
    )

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info("Transfer notification sent to %s (ticket %s)", email_dest, numero_chamado)
    else:
        logger.warning("Failed to send transfer notification to %s: %s", email_dest, err)


def notificar_supervisor_escalonamento_colega(
    chamado_id: str,
    numero_chamado: str,
    area: str,
    categoria: str,
    motivo: str,
    responsavel_usuario,
) -> None:
    """Notifica o colega que recebeu o escalonamento do chamado."""
    if not responsavel_usuario or not getattr(responsavel_usuario, "email", None):
        logger.debug("Escalation notification skipped: recipient has no e-mail")
        return

    email_dest = responsavel_usuario.email.strip()
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    motivo_truncado = (motivo or "")[:500] + ("..." if len(motivo or "") > 500 else "")
    cat_d = _tc(categoria)
    area_d = _ts(area)

    assunto = f"Ticket escalated to you: {numero_chamado}"

    detalhes_html = build_detail_table(
        [
            ("Number", numero_chamado),
            ("Category", cat_d),
            ("Area", area_d),
            ("Reason", motivo_truncado),
        ]
    )

    ctas = []
    if link:
        ctas.append(("View ticket", link, "#7c3aed"))
    if link_dash:
        ctas.append(("View sector tickets", link_dash, "#6b7280"))
    botoes_html = build_two_ctas(ctas) if ctas else ""

    corpo_html = build_email_shell(
        header_title="Ticket escalated to you",
        header_color="#7c3aed",
        body_html=(
            f"<p>Hello, a ticket in area <strong>{escape(area_d)}</strong> has been escalated to you.</p>"
            + detalhes_html
            + botoes_html
        ),
    )
    corpo_texto = (
        f"Number: {numero_chamado}\n"
        f"Category: {cat_d}\nArea: {area_d}\n"
        f"Reason: {motivo_truncado}" + (f"\n\nView ticket: {link}" if link else "")
    )

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info("Escalation notification sent to %s (ticket %s)", email_dest, numero_chamado)
    else:
        logger.warning("Failed to send escalation notification to %s: %s", email_dest, err)


# ---------------------------------------------------------------------------
# Participantes — Fase 4
# ---------------------------------------------------------------------------


def notificar_participante_incluido(
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    area: str,
    responsavel_usuario,
) -> None:
    """Notifica o supervisor que foi incluído como participante do chamado."""
    if not responsavel_usuario or not getattr(responsavel_usuario, "email", None):
        logger.debug("Participant inclusion notification skipped: recipient has no e-mail")
        return

    email_dest = responsavel_usuario.email.strip()
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    cat_d = _tc(categoria)
    area_d = _ts(area)

    assunto = f"You have been added as a participant: {numero_chamado}"

    detalhes_html = build_detail_table(
        [
            ("Number", numero_chamado),
            ("Category", cat_d),
            ("Area", area_d),
        ]
    )

    ctas = []
    if link:
        ctas.append(("View ticket", link, "#2563eb"))
    if link_dash:
        ctas.append(("View sector tickets", link_dash, "#6b7280"))
    botoes_html = build_two_ctas(ctas) if ctas else ""

    corpo_html = build_email_shell(
        header_title="You have been added as a participant",
        header_color="#2563eb",
        body_html=(
            f"<p>You have been added as a collaborating participant to a ticket in area "
            f"<strong>{escape(area_d)}</strong>. Please work on your part and mark it as done "
            f'using the <em>"Completed my part"</em> button.</p>' + detalhes_html + botoes_html
        ),
    )
    corpo_texto = (
        f"Number: {numero_chamado}\nCategory: {cat_d}\nArea: {area_d}\n\n"
        "You have been added as a collaborating participant. "
        "Please complete your part and mark it done." + (f"\n\nView ticket: {link}" if link else "")
    )

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info(
            "Participant inclusion notification sent to %s (ticket %s)", email_dest, numero_chamado
        )
    else:
        logger.warning(
            "Failed to send participant inclusion notification to %s: %s", email_dest, err
        )


# ---------------------------------------------------------------------------
# Escalada gerencial — Fase 6 (Escada A)
# ---------------------------------------------------------------------------


def notificar_escalada_resposta_gerencial(
    chamado_data: dict,
    chamado_id: str,
    nivel: int,
    email_dest: str,
) -> None:
    """Notifica gestor que um chamado Aberto excedeu o SLA de resposta (Escada A)."""
    numero_chamado = chamado_data.get("numero_chamado") or "N/A"
    categoria = chamado_data.get("categoria") or ""
    area = chamado_data.get("area") or ""
    tipo_solicitacao = chamado_data.get("tipo_solicitacao") or ""
    descricao_resumo = (chamado_data.get("descricao") or "")[:500]
    cat_d = _tc(categoria)
    area_d = _ts(area)
    tipo_d = _ts(tipo_solicitacao)

    nomes_nivel = {
        1: "Sector Manager",
        2: "Production Manager",
        3: "GM Assistant",
        4: "GM",
    }
    nome_nivel = nomes_nivel.get(nivel, f"Level {nivel}")

    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()

    assunto = f"[SLA Alert] Ticket {numero_chamado} — no response (Ladder A, Level {nivel})"

    detalhes_html = build_detail_table(
        [
            ("Number", numero_chamado),
            ("Category", cat_d),
            ("Type", tipo_d),
            ("Area", area_d),
            ("Escalation Level", f"{nivel} — {nome_nivel}"),
        ]
    )
    summary_html = (
        f'<p style="margin: 12px 0;">{escape(descricao_resumo)}</p>' if descricao_resumo else ""
    )

    ctas = []
    if link:
        ctas.append(("View ticket history", link, "#dc2626"))
    if link_dash:
        ctas.append(("View all tickets", link_dash, "#6b7280"))
    botoes_html = build_two_ctas(ctas) if ctas else ""

    corpo_html = build_email_shell(
        header_title=f"SLA Alert — Ticket {escape(numero_chamado)} without response",
        header_color="#dc2626",
        body_html=(
            f"<p>This ticket has been open for over <strong>{nivel} business hour(s)</strong> "
            f"without being attended to. This notification is addressed to the "
            f"<strong>{nome_nivel}</strong>.</p>" + detalhes_html + summary_html + botoes_html
        ),
    )
    corpo_texto = (
        f"SLA Alert — Ticket {numero_chamado} without response.\n"
        f"Escalation Level {nivel} ({nome_nivel}).\n"
        f"Category: {cat_d}\nArea: {area_d}" + (f"\n\nView ticket: {link}" if link else "")
    )

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info(
            "SLA escalation (level %d) sent to %s (ticket %s)", nivel, email_dest, numero_chamado
        )
    else:
        logger.warning("Failed to send SLA escalation notification to %s: %s", email_dest, err)


def notificar_owner_todos_participantes_concluiram(
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    owner_usuario,
) -> None:
    """Notifica o owner que todos os participantes concluíram — chamado pode ser fechado."""
    if not owner_usuario or not getattr(owner_usuario, "email", None):
        logger.debug("Owner all-done notification skipped: owner has no e-mail")
        return

    email_dest = owner_usuario.email.strip()
    nome_owner = getattr(owner_usuario, "nome", None) or "Responsible"
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    cat_d = _tc(categoria)

    assunto = f"Ticket {numero_chamado}: all participants completed their part"

    detalhes_html = build_detail_table(
        [
            ("Number", numero_chamado),
            ("Category", cat_d),
        ]
    )

    ctas = []
    if link:
        ctas.append(("Close ticket", link, "#16a34a"))
    if link_dash:
        ctas.append(("View sector tickets", link_dash, "#6b7280"))
    botoes_html = build_two_ctas(ctas) if ctas else ""

    corpo_html = build_email_shell(
        header_title="All participants completed their part",
        header_color="#16a34a",
        body_html=(
            f"<p>Hello, <strong>{escape(nome_owner)}</strong>! "
            f"All collaborating participants of ticket <strong>{escape(numero_chamado)}</strong> "
            f"have completed their part. You can now close the ticket.</p>"
            + detalhes_html
            + botoes_html
        ),
    )
    corpo_texto = (
        f"Hello, {nome_owner}!\n\n"
        f"All participants of ticket {numero_chamado} ({cat_d}) have completed their part.\n"
        "You can now close the ticket." + (f"\n\nView ticket: {link}" if link else "")
    )

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info(
            "All-done owner notification sent to %s (ticket %s)", email_dest, numero_chamado
        )
    else:
        logger.warning("Failed to send all-done notification to %s: %s", email_dest, err)


# ---------------------------------------------------------------------------
# SLA Resolução — Fase 7 (Escada B)
# ---------------------------------------------------------------------------


def notificar_aviso_resolucao_supervisor(
    chamado_data: dict,
    chamado_id: str,
    marco: int,
    responsavel_id: str,
    email_dest: str | None = None,
) -> None:
    """Avisa o supervisor responsável que o prazo de resolução atingiu um marco percentual.

    Dispara sempre: notificação in-app + Web Push (quando responsavel_id presente).
    E-mail somente quando email_dest for truthy.
    marco: 50 ou 80 (percentual do SLA de resolução consumido).
    """
    numero_chamado = chamado_data.get("numero_chamado") or "N/A"
    categoria = chamado_data.get("categoria") or ""
    area = chamado_data.get("area") or ""
    tipo_solicitacao = chamado_data.get("tipo_solicitacao") or ""
    descricao_resumo = (chamado_data.get("descricao") or "")[:500]
    cat_d = _tc(categoria)
    area_d = _ts(area)
    tipo_d = _ts(tipo_solicitacao)

    assunto = f"[SLA {marco}%] Ticket {numero_chamado} — resolution deadline approaching"
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()

    # Notificação in-app
    if responsavel_id:
        try:
            from app.services.notifications_inapp import criar_notificacao

            criar_notificacao(
                usuario_id=responsavel_id,
                chamado_id=chamado_id,
                numero_chamado=numero_chamado,
                titulo=assunto,
                mensagem=f"Ticket {numero_chamado} is at {marco}% of the resolution SLA deadline.",
                tipo="sla_resolucao",
                categoria=categoria,
            )
        except Exception as exc:
            logger.warning("In-app SLA %d%% warning failed (ticket %s): %s", marco, chamado_id, exc)

        # Web Push
        try:
            from app.services.webpush_service import enviar_webpush_usuario

            enviar_webpush_usuario(
                usuario_id=responsavel_id,
                titulo=assunto,
                corpo=f"Ticket {numero_chamado} is at {marco}% of the resolution deadline.",
                url=link or None,
            )
        except Exception as exc:
            logger.warning(
                "WebPush SLA %d%% warning failed (ticket %s): %s", marco, chamado_id, exc
            )

    detalhes_html = build_detail_table(
        [
            ("Number", numero_chamado),
            ("Category", cat_d),
            ("Type", tipo_d),
            ("Area", area_d),
            ("SLA Progress", f"{marco}%"),
        ]
    )
    summary_html = (
        f'<p style="margin: 12px 0;">{escape(descricao_resumo)}</p>' if descricao_resumo else ""
    )

    ctas = []
    if link:
        ctas.append(("View ticket history", link, "#d97706"))
    if link_dash:
        ctas.append(("View all tickets", link_dash, "#6b7280"))
    botoes_html = build_two_ctas(ctas) if ctas else ""

    corpo_html = build_email_shell(
        header_title=f"SLA Warning — {marco}% of resolution deadline consumed",
        header_color="#d97706",
        body_html=(
            f"<p>Ticket <strong>{escape(numero_chamado)}</strong> has consumed "
            f"<strong>{marco}%</strong> of its resolution SLA deadline.</p>"
            + detalhes_html
            + summary_html
            + botoes_html
        ),
    )
    corpo_texto = (
        f"SLA Warning — Ticket {numero_chamado}.\n"
        f"Resolution deadline: {marco}% consumed.\n"
        f"Category: {cat_d}\nArea: {area_d}" + (f"\n\nView ticket: {link}" if link else "")
    )

    if email_dest:
        ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto)
        if ok:
            logger.info(
                "SLA %d%% warning sent to %s (ticket %s)", marco, email_dest, numero_chamado
            )
        else:
            logger.warning("Failed to send SLA %d%% warning to %s: %s", marco, email_dest, err)


def notificar_escalada_resolucao_gerencial(
    chamado_data: dict,
    chamado_id: str,
    nivel: int,
    email_dest: str,
) -> None:
    """Notifica gestor que um chamado Em Atendimento excedeu o prazo de resolução (Escada B)."""
    numero_chamado = chamado_data.get("numero_chamado") or "N/A"
    categoria = chamado_data.get("categoria") or ""
    area = chamado_data.get("area") or ""
    tipo_solicitacao = chamado_data.get("tipo_solicitacao") or ""
    descricao_resumo = (chamado_data.get("descricao") or "")[:500]
    cat_d = _tc(categoria)
    area_d = _ts(area)
    tipo_d = _ts(tipo_solicitacao)

    nomes_nivel = {
        1: "Sector Manager",
        2: "Production Manager",
        3: "GM Assistant",
        4: "GM",
    }
    nome_nivel = nomes_nivel.get(nivel, f"Level {nivel}")

    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()

    assunto = f"[SLA Alert] Ticket {numero_chamado} — resolution overdue (Ladder B, Level {nivel})"

    detalhes_html = build_detail_table(
        [
            ("Number", numero_chamado),
            ("Category", cat_d),
            ("Type", tipo_d),
            ("Area", area_d),
            ("Escalation Level", f"{nivel} — {nome_nivel}"),
        ]
    )
    summary_html = (
        f'<p style="margin: 12px 0;">{escape(descricao_resumo)}</p>' if descricao_resumo else ""
    )

    ctas = []
    if link:
        ctas.append(("View ticket history", link, "#dc2626"))
    if link_dash:
        ctas.append(("View all tickets", link_dash, "#6b7280"))
    botoes_html = build_two_ctas(ctas) if ctas else ""

    corpo_html = build_email_shell(
        header_title=f"SLA Alert — Ticket {escape(numero_chamado)} resolution overdue",
        header_color="#dc2626",
        body_html=(
            f"<p>Ticket <strong>{escape(numero_chamado)}</strong> is overdue for resolution. "
            f"This notification is addressed to the <strong>{nome_nivel}</strong>.</p>"
            + detalhes_html
            + summary_html
            + botoes_html
        ),
    )
    corpo_texto = (
        f"SLA Alert — Ticket {numero_chamado} resolution overdue.\n"
        f"Escalation Level {nivel} ({nome_nivel}).\n"
        f"Category: {cat_d}\nArea: {area_d}" + (f"\n\nView ticket: {link}" if link else "")
    )

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info(
            "SLA resolution escalation (level %d) sent to %s (ticket %s)",
            nivel,
            email_dest,
            numero_chamado,
        )
    else:
        logger.warning("Failed to send SLA resolution escalation to %s: %s", email_dest, err)
