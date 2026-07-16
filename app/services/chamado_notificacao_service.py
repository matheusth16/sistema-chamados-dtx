"""
Fan-out centralizado de notificações de chamado.

  destinatarios_do_chamado(dados) → [Usuario, ...] (responsável + observadores)
  notificar_cancelamento_chamado(...)  → envia email a todos os destinatários
"""

import logging
from html import escape

from app.i18n import get_translated_status, get_translation
from app.models_usuario import Usuario
from app.services import webpush_service
from app.services.email_templates import build_cta_button, build_detail_table, build_email_shell
from app.services.notifications import enviar_email
from app.services.notifications_inapp import criar_notificacao

logger = logging.getLogger(__name__)


def destinatarios_do_chamado(dados_chamado: dict) -> list:
    """
    Resolve e retorna a lista de usuários a notificar para um chamado:
    o responsável (se existir e for encontrado) + cada observador.

    Deduplicado por usuario.id — se o responsável também é observador, aparece
    apenas uma vez. Usuários não encontrados são silenciosamente omitidos.
    """
    destinatarios: list = []
    vistos: set = set()

    responsavel_id = dados_chamado.get("responsavel_id")
    if responsavel_id:
        responsavel = Usuario.get_by_id(responsavel_id)
        if responsavel:
            destinatarios.append(responsavel)
            vistos.add(responsavel.id)

    for obs in dados_chamado.get("observadores") or []:
        uid = obs.get("usuario_id") if isinstance(obs, dict) else getattr(obs, "usuario_id", None)
        if not uid or uid in vistos:
            continue
        usuario = Usuario.get_by_id(uid)
        if usuario:
            destinatarios.append(usuario)
            vistos.add(usuario.id)

    return destinatarios


def notificar_cancelamento_chamado(
    *,
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    motivo: str,
    solicitante_nome: str,
    dados_chamado: dict,
) -> None:
    """Envia email, in-app e web push de cancelamento para responsável + observadores."""
    destinatarios = destinatarios_do_chamado(dados_chamado)
    if not destinatarios:
        logger.info("Cancellation CH %s: no recipients, no e-mail sent.", numero_chamado)
        return

    assunto = get_translation(
        "push_subject_cancelled", "en", numero=numero_chamado, categoria=categoria
    )
    link = _link_chamado(chamado_id)

    for usuario in destinatarios:
        email = getattr(usuario, "email", None)
        uid = getattr(usuario, "id", None)

        if email:
            corpo_html = build_email_shell(
                f"Ticket {numero_chamado} Cancelled",
                "#dc2626",
                f"<p>Ticket <strong>{escape(numero_chamado)}</strong> was <strong>cancelled</strong>"
                f" by the requester <em>{escape(solicitante_nome)}</em>.</p>"
                + build_detail_table(
                    [
                        ("Ticket", numero_chamado),
                        ("Category", categoria),
                        ("Reason", motivo),
                        ("Cancelled by", solicitante_nome),
                    ]
                )
                + (build_cta_button("View ticket", link, "#2563eb") if link else ""),
            )
            corpo_texto = (
                f"Ticket {numero_chamado} cancelled by {solicitante_nome}.\n"
                f"Reason: {motivo}\nCategory: {categoria}"
                + (f"\n\nView ticket: {link}" if link else "")
            )
            ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="normal")
            if ok:
                logger.info("Cancellation e-mail sent to %s (ticket %s)", email, numero_chamado)
            else:
                logger.warning(
                    "Failed to send cancellation e-mail to %s (ticket %s): %s",
                    email,
                    numero_chamado,
                    err,
                )

        if uid:
            criar_notificacao(
                usuario_id=uid,
                chamado_id=chamado_id,
                numero_chamado=numero_chamado,
                titulo=f"Chamado {numero_chamado} cancelado",
                mensagem=categoria,
                tipo="observador_cancelamento",
                categoria=categoria,
            )
            webpush_service.enviar_webpush_usuario(
                uid,
                titulo=assunto,
                corpo=categoria,
                url=link or "",
            )


def notificar_edicao_descricao_solicitante(
    *,
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    solicitante_nome: str,
    valor_anterior: str,
    valor_novo: str,
    dados_chamado: dict,
) -> None:
    """Notifica responsável + observadores quando o solicitante edita a descrição."""
    destinatarios = destinatarios_do_chamado(dados_chamado)
    if not destinatarios:
        logger.info("Description edit CH %s: no recipients, no e-mail sent.", numero_chamado)
        return

    assunto = get_translation("push_subject_updated", "en", numero=numero_chamado)
    link = _link_chamado(chamado_id)
    _max_chars = 300

    anterior_trunc = (valor_anterior or "")[:_max_chars]
    novo_trunc = (valor_novo or "")[:_max_chars]

    for usuario in destinatarios:
        email = getattr(usuario, "email", None)
        uid = getattr(usuario, "id", None)

        if email:
            corpo_html = build_email_shell(
                f"Ticket {numero_chamado} — Description Edited",
                "#2563eb",
                f"<p>The requester <em>{escape(solicitante_nome)}</em> edited the description of ticket "
                f"<strong>{escape(numero_chamado)}</strong> ({escape(categoria)}).</p>"
                + build_detail_table(
                    [
                        ("Ticket", numero_chamado),
                        ("Category", categoria),
                        ("Edited by", solicitante_nome),
                        ("Previous description", anterior_trunc),
                        ("New description", novo_trunc),
                    ]
                )
                + (build_cta_button("View ticket", link, "#2563eb") if link else ""),
            )
            corpo_texto = (
                f"Ticket {numero_chamado} — description edited by {solicitante_nome}.\n"
                f"Previous: {anterior_trunc}\nNew: {novo_trunc}"
                + (f"\n\nView ticket: {link}" if link else "")
            )
            ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="normal")
            if ok:
                logger.info("Description edit e-mail sent to %s (ticket %s)", email, numero_chamado)
            else:
                logger.warning(
                    "Failed to send description edit e-mail to %s (ticket %s): %s",
                    email,
                    numero_chamado,
                    err,
                )

        if uid:
            criar_notificacao(
                usuario_id=uid,
                chamado_id=chamado_id,
                numero_chamado=numero_chamado,
                titulo=f"Descrição editada — Chamado {numero_chamado}",
                mensagem=categoria,
                tipo="observador_edicao_descricao",
                categoria=categoria,
            )
            webpush_service.enviar_webpush_usuario(
                uid,
                titulo=assunto,
                corpo=categoria,
                url=link or "",
            )


def notificar_observadores_criacao(
    *,
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    solicitante_nome: str,
    observadores: list,
) -> None:
    """Notifica observadores incluídos no momento da criação do chamado."""
    if not observadores:
        return

    assunto = get_translation("push_subject_cc", "en", numero=numero_chamado, categoria=categoria)
    link = _link_chamado(chamado_id)

    for obs in observadores:
        uid = obs.get("usuario_id") if isinstance(obs, dict) else getattr(obs, "usuario_id", None)
        if not uid:
            continue

        usuario = Usuario.get_by_id(uid)
        if not usuario:
            continue

        email = getattr(usuario, "email", None)
        nome = getattr(usuario, "nome", None)

        if email:
            corpo_html = build_email_shell(
                f"Ticket {numero_chamado} — You are an observer",
                "#7c3aed",
                f"<p>Hello{f' {escape(nome)}' if nome else ''},</p>"
                f"<p>You have been added as an <strong>observer</strong> of ticket "
                f"<strong>{escape(numero_chamado)}</strong> ({escape(categoria)}) opened by "
                f"<em>{escape(solicitante_nome)}</em>.</p>"
                "<p>You will receive notifications about updates to this ticket.</p>"
                + build_detail_table(
                    [
                        ("Ticket", numero_chamado),
                        ("Category", categoria),
                        ("Opened by", solicitante_nome),
                    ]
                )
                + (build_cta_button("View ticket", link, "#2563eb") if link else ""),
            )
            corpo_texto = (
                f"You have been added as an observer of ticket {numero_chamado} ({categoria})"
                f" opened by {solicitante_nome}." + (f"\n\nView ticket: {link}" if link else "")
            )
            ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="normal")
            if ok:
                logger.info(
                    "Observer inclusion e-mail sent to %s (ticket %s)", email, numero_chamado
                )
            else:
                logger.warning(
                    "Failed to send observer inclusion e-mail to %s (ticket %s): %s",
                    email,
                    numero_chamado,
                    err,
                )

        criar_notificacao(
            usuario_id=uid,
            chamado_id=chamado_id,
            numero_chamado=numero_chamado,
            titulo=f"Você é observador — Chamado {numero_chamado}",
            mensagem=categoria,
            tipo="observador_incluido",
            categoria=categoria,
        )
        webpush_service.enviar_webpush_usuario(
            uid,
            titulo=assunto,
            corpo=categoria,
            url=link or "",
        )


def notificar_observadores_mudanca_status(
    *,
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    novo_status: str,
    dados_chamado: dict,
) -> None:
    """Notifica responsável + observadores (fan-out) quando status muda para Em Atendimento/Concluído."""
    destinatarios = destinatarios_do_chamado(dados_chamado)
    if not destinatarios:
        logger.info(
            "Status %s CH %s: no recipients, no notification sent.",
            novo_status,
            numero_chamado,
        )
        return

    status_en = get_translated_status(novo_status, "en")
    assunto = get_translation(
        "push_subject_status_change",
        "en",
        status=status_en,
        numero=numero_chamado,
        categoria=categoria,
    )
    link = _link_chamado(chamado_id)

    for usuario in destinatarios:
        email = getattr(usuario, "email", None)
        uid = getattr(usuario, "id", None)

        if email:
            corpo_html = build_email_shell(
                f"Ticket {numero_chamado}: {status_en}",
                "#2563eb",
                f"<p>The status of ticket <strong>{escape(numero_chamado)}</strong> ({escape(categoria)}) "
                f"was updated to <strong>{escape(status_en)}</strong>.</p>"
                + build_detail_table(
                    [
                        ("Ticket", numero_chamado),
                        ("Category", categoria),
                        ("New status", status_en),
                    ]
                )
                + (build_cta_button("View ticket", link, "#2563eb") if link else ""),
            )
            corpo_texto = f"Ticket {numero_chamado} — status updated to {status_en}." + (
                f"\n\nView ticket: {link}" if link else ""
            )
            ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="normal")
            if ok:
                logger.info(
                    "Status %s e-mail sent to %s (ticket %s)",
                    status_en,
                    email,
                    numero_chamado,
                )
            else:
                logger.warning(
                    "Failed to send status %s e-mail to %s (ticket %s): %s",
                    status_en,
                    email,
                    numero_chamado,
                    err,
                )

        if uid:
            tipo = (
                "observador_status_concluido"
                if novo_status == "Concluído"
                else "observador_status_em_atendimento"
            )
            criar_notificacao(
                usuario_id=uid,
                chamado_id=chamado_id,
                numero_chamado=numero_chamado,
                titulo=f"Chamado {numero_chamado}: {novo_status}",
                mensagem=categoria,
                tipo=tipo,
                categoria=categoria,
            )
            webpush_service.enviar_webpush_usuario(
                uid,
                titulo=assunto,
                corpo=categoria,
                url=link or "",
            )


def notificar_anexo_tardio_chamado(
    *,
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    solicitante_nome: str,
    nome_arquivo: str,
    motivo: str,
    dados_chamado: dict,
) -> None:
    """Notifica responsável + observadores quando solicitante adiciona anexo tardio."""
    destinatarios = destinatarios_do_chamado(dados_chamado)
    if not destinatarios:
        logger.info("Late attachment CH %s: no recipients, no e-mail sent.", numero_chamado)
        return

    assunto = get_translation("push_subject_attachment", "en", numero=numero_chamado)
    link = _link_chamado(chamado_id)

    for usuario in destinatarios:
        email = getattr(usuario, "email", None)
        uid = getattr(usuario, "id", None)

        if email:
            corpo_html = build_email_shell(
                f"Ticket {numero_chamado} — New Attachment",
                "#0891b2",
                f"<p>The requester <em>{escape(solicitante_nome)}</em> added a new attachment to ticket "
                f"<strong>{escape(numero_chamado)}</strong> ({escape(categoria)}).</p>"
                + build_detail_table(
                    [
                        ("Ticket", numero_chamado),
                        ("Category", categoria),
                        ("File", nome_arquivo),
                        ("Reason", motivo),
                        ("Added by", solicitante_nome),
                    ]
                )
                + (build_cta_button("View ticket", link, "#2563eb") if link else ""),
            )
            corpo_texto = (
                f"Ticket {numero_chamado} — new attachment added by {solicitante_nome}.\n"
                f"File: {nome_arquivo}\nReason: {motivo}"
                + (f"\n\nView ticket: {link}" if link else "")
            )
            ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="normal")
            if ok:
                logger.info("Late attachment e-mail sent to %s (ticket %s)", email, numero_chamado)
            else:
                logger.warning(
                    "Failed to send late attachment e-mail to %s (ticket %s): %s",
                    email,
                    numero_chamado,
                    err,
                )

        if uid:
            criar_notificacao(
                usuario_id=uid,
                chamado_id=chamado_id,
                numero_chamado=numero_chamado,
                titulo=f"Novo anexo — Chamado {numero_chamado}",
                mensagem=categoria,
                tipo="observador_anexo_tardio",
                categoria=categoria,
            )
            webpush_service.enviar_webpush_usuario(
                uid,
                titulo=assunto,
                corpo=categoria,
                url=link or "",
            )


def notificar_resposta_solicitante_chamado(
    *,
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    solicitante_nome: str,
    mensagem: str,
    dados_chamado: dict,
) -> None:
    """Notifica responsável + observadores quando o solicitante responde em texto livre."""
    destinatarios = destinatarios_do_chamado(dados_chamado)
    if not destinatarios:
        logger.info("Reply CH %s: no recipients, no e-mail sent.", numero_chamado)
        return

    assunto = get_translation("push_subject_reply", "en", numero=numero_chamado)
    link = _link_chamado(chamado_id)

    for usuario in destinatarios:
        email = getattr(usuario, "email", None)
        uid = getattr(usuario, "id", None)

        if email:
            corpo_html = build_email_shell(
                f"Ticket {numero_chamado} — New Reply",
                "#0891b2",
                f"<p>The requester <em>{escape(solicitante_nome)}</em> replied to ticket "
                f"<strong>{escape(numero_chamado)}</strong> ({escape(categoria)}).</p>"
                + build_detail_table(
                    [
                        ("Ticket", numero_chamado),
                        ("Category", categoria),
                        ("Message", mensagem),
                        ("Replied by", solicitante_nome),
                    ]
                )
                + (build_cta_button("View ticket", link, "#2563eb") if link else ""),
            )
            corpo_texto = (
                f"Ticket {numero_chamado} — new reply from {solicitante_nome}.\n"
                f"Message: {mensagem}" + (f"\n\nView ticket: {link}" if link else "")
            )
            ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="normal")
            if ok:
                logger.info("Reply e-mail sent to %s (ticket %s)", email, numero_chamado)
            else:
                logger.warning(
                    "Failed to send reply e-mail to %s (ticket %s): %s",
                    email,
                    numero_chamado,
                    err,
                )

        if uid:
            criar_notificacao(
                usuario_id=uid,
                chamado_id=chamado_id,
                numero_chamado=numero_chamado,
                titulo=f"Nova resposta — Chamado {numero_chamado}",
                mensagem=categoria,
                tipo="observador_resposta_solicitante",
                categoria=categoria,
            )
            webpush_service.enviar_webpush_usuario(
                uid,
                titulo=assunto,
                corpo=categoria,
                url=link or "",
            )


def _link_chamado(chamado_id: str) -> str:
    try:
        from flask import current_app, url_for

        with current_app.test_request_context():
            return url_for("main.visualizar_chamado", chamado_id=chamado_id, _external=True)
    except Exception:
        return ""
