"""Notificações de ciclo de vida do chamado: criação, prazo, status, confirmação, reabertura, transferência, participantes."""

import logging
from html import escape

from app.services.email_templates import (
    build_cta_button,
    build_detail_table,
    build_email_shell,
    build_two_ctas,
)
from app.services.notifications_core import (
    _link_chamado,
    _link_dashboard,
    _link_historico,
    _prefixar_assunto_high,
    _tc,
    _ts,
    _tsl,
    _tst,
    enviar_email,
    resolver_importance,
)

logger = logging.getLogger(__name__)


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
    prioridade: int | None = None,
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

    importance = resolver_importance(
        "novo_chamado_aprovador",
        chamado_data={"categoria": categoria, "prioridade": prioridade},
        destinatario_perfil="responsavel",
    )
    assunto = f"New ticket assigned: {numero_chamado}"
    if importance == "high":
        assunto = _prefixar_assunto_high(assunto, "novo_chamado_projetos")

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

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto, importance=importance)
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

    ok, err = enviar_email(
        email_dest,
        assunto,
        corpo_html,
        corpo_texto,
        importance=resolver_importance("prazo_24h"),
    )
    if ok:
        logger.info("24h alert sent to %s (ticket %s)", email_dest, numero_chamado)
    else:
        logger.warning("Failed to send 24h alert to %s: %s", email_dest, err)


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

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto, importance="normal")
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

        ok, err = enviar_email(email.strip(), assunto, corpo_html, corpo_texto, importance="normal")
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

    ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="normal")
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

    ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="normal")
    if ok:
        logger.info("Confirmation request sent to %s (ticket %s)", email, numero_chamado)
    else:
        logger.warning("Failed to send confirmation request to %s: %s", email, err)


# ---------------------------------------------------------------------------
# Reminder — requester still hasn't confirmed resolution
# ---------------------------------------------------------------------------


def notificar_solicitante_lembrete_confirmacao(
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    solicitante_usuario,
    numero_lembrete: int = 1,
) -> bool:
    """Send a reminder to the requester that the ticket is still awaiting their confirmation.

    Returns True if the e-mail was sent successfully, False otherwise.
    """
    if not solicitante_usuario:
        return False
    email = (getattr(solicitante_usuario, "email", None) or "").strip()
    if not email:
        return False

    nome = getattr(solicitante_usuario, "nome", None) or "Requester"
    link = _link_chamado(chamado_id)
    cat_d = _tc(categoria)

    assunto = f"Reminder #{numero_lembrete}: ticket {numero_chamado} awaiting your confirmation"

    detalhes_html = build_detail_table(
        [("Ticket", numero_chamado), ("Category", cat_d), ("Status", "Completed")]
    )
    botoes_html = (
        f'<p style="margin-top:20px;">{build_cta_button("Confirm or reopen", link, "#059669")}</p>'
        if link
        else ""
    )

    corpo_html = build_email_shell(
        header_title=f"Reminder: ticket {numero_chamado} needs your attention",
        header_color="#d97706",
        body_html=(
            f"<p>Hello, <strong>{escape(nome)}</strong>! "
            f"This is reminder <strong>#{numero_lembrete}</strong>. "
            "Ticket <strong>"
            f"{escape(numero_chamado)}</strong> was marked as <strong>completed</strong> "
            "but still awaits your confirmation. "
            "Please open it to confirm or reopen.</p>" + detalhes_html + botoes_html
        ),
    )
    corpo_texto = (
        f"Hello, {nome}!\n\n"
        f"Reminder #{numero_lembrete}: ticket {numero_chamado} is still awaiting your "
        f"confirmation.\nCategory: {cat_d}\nStatus: Completed\n\n"
        "Please confirm whether the issue was resolved or reopen it."
        + (f"\n\nOpen ticket: {link}" if link else "")
    )

    ok, err = enviar_email(
        email,
        assunto,
        corpo_html,
        corpo_texto,
        importance=resolver_importance("lembrete_confirmacao", numero_lembrete=numero_lembrete),
    )
    if ok:
        logger.info(
            "Confirmation reminder #%s sent to %s (ticket %s)",
            numero_lembrete,
            email,
            numero_chamado,
        )
        return True
    else:
        logger.warning(
            "Failed to send confirmation reminder #%s to %s: %s",
            numero_lembrete,
            email,
            err,
        )
        return False


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
    link = _link_historico(chamado_id)
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

    ok, err = enviar_email(
        email,
        assunto,
        corpo_html,
        corpo_texto,
        importance=resolver_importance("chamado_reaberto"),
    )
    if ok:
        logger.info("Reopen notification sent to %s (ticket %s)", email, numero_chamado)
    else:
        logger.warning("Failed to send reopen notification to %s: %s", email, err)


# ---------------------------------------------------------------------------
# Ticket confirmed by requester — notify responsible
# ---------------------------------------------------------------------------


def notificar_responsavel_chamado_confirmado(
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    solicitante_nome: str,
    responsavel_usuario,
) -> None:
    """Notify the responsible that the requester confirmed the ticket was resolved."""
    if not responsavel_usuario:
        return
    email = (getattr(responsavel_usuario, "email", None) or "").strip()
    if not email:
        return

    nome_responsavel = getattr(responsavel_usuario, "nome", None) or "Responsible"
    link = _link_historico(chamado_id)
    link_dash = _link_dashboard()
    cat_d = _tc(categoria)

    assunto = f"Ticket {numero_chamado}: requester confirmed resolution"

    detalhes_html = build_detail_table(
        [
            ("Ticket", numero_chamado),
            ("Category", cat_d),
            ("Requester", escape(solicitante_nome)),
            ("Status", "Confirmed — resolved"),
        ]
    )

    ctas = []
    if link:
        ctas.append(("View ticket history", link, "#059669"))
    if link_dash:
        ctas.append(("View sector tickets", link_dash, "#6b7280"))
    botoes_html = build_two_ctas(ctas) if ctas else ""

    corpo_html = build_email_shell(
        header_title=f"Ticket {numero_chamado}: confirmed resolved",
        header_color="#059669",
        body_html=(
            f"<p>Hello, <strong>{escape(nome_responsavel)}</strong>! "
            f"The requester <strong>{escape(solicitante_nome)}</strong> has confirmed that "
            f"ticket <strong>{escape(numero_chamado)}</strong> was successfully resolved. "
            "No further action is required.</p>" + detalhes_html + botoes_html
        ),
    )
    corpo_texto = (
        f"Hello, {nome_responsavel}!\n\n"
        f"Ticket {numero_chamado} was confirmed as resolved by {solicitante_nome}.\n"
        f"Category: {cat_d}\nStatus: Confirmed — resolved"
        + (f"\n\nView ticket: {link}" if link else "")
    )

    ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="normal")
    if ok:
        logger.info("Confirmation notification sent to %s (ticket %s)", email, numero_chamado)
    else:
        logger.warning("Failed to send confirmation notification to %s: %s", email, err)


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

    ok, err = enviar_email(
        email_dest,
        assunto,
        corpo_html,
        corpo_texto,
        importance=resolver_importance("transferencia_area"),
    )
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

    ok, err = enviar_email(
        email_dest,
        assunto,
        corpo_html,
        corpo_texto,
        importance=resolver_importance("escalonamento_colega"),
    )
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

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto, importance="normal")
    if ok:
        logger.info(
            "Participant inclusion notification sent to %s (ticket %s)", email_dest, numero_chamado
        )
    else:
        logger.warning(
            "Failed to send participant inclusion notification to %s: %s", email_dest, err
        )


# ---------------------------------------------------------------------------
# Escalada gerencial — Fase 6 (Escada A) — movida para notifications_escalonamento.py
# ---------------------------------------------------------------------------


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

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto, importance="normal")
    if ok:
        logger.info(
            "All-done owner notification sent to %s (ticket %s)", email_dest, numero_chamado
        )
    else:
        logger.warning("Failed to send all-done notification to %s: %s", email_dest, err)
