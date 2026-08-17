"""
Fan-out centralizado de notificações de chamado.

  destinatarios_do_chamado(dados) → [Usuario, ...] (responsável + observadores)
  notificar_cancelamento_chamado(...)  → envia email a todos os destinatários
"""

import logging
from html import escape

from app.i18n import get_translated_category, get_translated_status, get_translation
from app.models_usuario import Usuario
from app.services import webpush_service
from app.services.email_templates import (
    build_cta_button,
    build_detail_table,
    build_email_shell,
    build_two_ctas,
)
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

    categoria_en = get_translated_category(categoria, "en")
    assunto = get_translation(
        "push_subject_cancelled", "en", numero=numero_chamado, categoria=categoria_en
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
                        ("Category", categoria_en),
                        ("Reason", motivo),
                        ("Cancelled by", solicitante_nome),
                    ]
                )
                + (build_cta_button("View ticket", link, "#2563eb") if link else ""),
            )
            corpo_texto = (
                f"Ticket {numero_chamado} cancelled by {solicitante_nome}.\n"
                f"Reason: {motivo}\nCategory: {categoria_en}"
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

    categoria_en = get_translated_category(categoria, "en")
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
                f"<strong>{escape(numero_chamado)}</strong> ({escape(categoria_en)}).</p>"
                + build_detail_table(
                    [
                        ("Ticket", numero_chamado),
                        ("Category", categoria_en),
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

    categoria_en = get_translated_category(categoria, "en")
    assunto = get_translation(
        "push_subject_cc", "en", numero=numero_chamado, categoria=categoria_en
    )
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
                f"<strong>{escape(numero_chamado)}</strong> ({escape(categoria_en)}) opened by "
                f"<em>{escape(solicitante_nome)}</em>.</p>"
                "<p>You will receive notifications about updates to this ticket.</p>"
                + build_detail_table(
                    [
                        ("Ticket", numero_chamado),
                        ("Category", categoria_en),
                        ("Opened by", solicitante_nome),
                    ]
                )
                + (build_cta_button("View ticket", link, "#2563eb") if link else ""),
            )
            corpo_texto = (
                f"You have been added as an observer of ticket {numero_chamado} ({categoria_en})"
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
    categoria_en = get_translated_category(categoria, "en")
    assunto = get_translation(
        "push_subject_status_change",
        "en",
        status=status_en,
        numero=numero_chamado,
        categoria=categoria_en,
    )
    link = _link_chamado(chamado_id)

    for usuario in destinatarios:
        email = getattr(usuario, "email", None)
        uid = getattr(usuario, "id", None)

        if email:
            corpo_html = build_email_shell(
                f"Ticket {numero_chamado}: {status_en}",
                "#2563eb",
                f"<p>The status of ticket <strong>{escape(numero_chamado)}</strong> ({escape(categoria_en)}) "
                f"was updated to <strong>{escape(status_en)}</strong>.</p>"
                + build_detail_table(
                    [
                        ("Ticket", numero_chamado),
                        ("Category", categoria_en),
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

    categoria_en = get_translated_category(categoria, "en")
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
                f"<strong>{escape(numero_chamado)}</strong> ({escape(categoria_en)}).</p>"
                + build_detail_table(
                    [
                        ("Ticket", numero_chamado),
                        ("Category", categoria_en),
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

    categoria_en = get_translated_category(categoria, "en")
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
                f"<strong>{escape(numero_chamado)}</strong> ({escape(categoria_en)}).</p>"
                + build_detail_table(
                    [
                        ("Ticket", numero_chamado),
                        ("Category", categoria_en),
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


def destinatarios_para_resposta_supervisor(dados_chamado: dict) -> list:
    """Resolve e retorna os usuários a notificar quando o RESPONSÁVEL (supervisor/
    admin) responde em texto livre: o solicitante dono + cada observador — via
    inversa de destinatarios_do_chamado (usada quando quem responde é o solicitante).

    Deduplicado por usuario.id. Usuários não encontrados são silenciosamente omitidos.
    """
    destinatarios: list = []
    vistos: set = set()

    solicitante_id = dados_chamado.get("solicitante_id")
    if solicitante_id:
        solicitante = Usuario.get_by_id(solicitante_id)
        if solicitante:
            destinatarios.append(solicitante)
            vistos.add(solicitante.id)

    for obs in dados_chamado.get("observadores") or []:
        uid = obs.get("usuario_id") if isinstance(obs, dict) else getattr(obs, "usuario_id", None)
        if not uid or uid in vistos:
            continue
        usuario = Usuario.get_by_id(uid)
        if usuario:
            destinatarios.append(usuario)
            vistos.add(usuario.id)

    return destinatarios


def notificar_resposta_supervisor_chamado(
    *,
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    respondente_nome: str,
    mensagem: str,
    dados_chamado: dict,
) -> None:
    """Notifica solicitante + observadores quando o responsável (supervisor/admin)
    responde em texto livre — via inversa de notificar_resposta_solicitante_chamado."""
    destinatarios = destinatarios_para_resposta_supervisor(dados_chamado)
    if not destinatarios:
        logger.info("Reply CH %s: no recipients, no e-mail sent.", numero_chamado)
        return

    categoria_en = get_translated_category(categoria, "en")
    assunto = get_translation("push_subject_reply_supervisor", "en", numero=numero_chamado)
    link = _link_chamado(chamado_id)

    for usuario in destinatarios:
        email = getattr(usuario, "email", None)
        uid = getattr(usuario, "id", None)

        if email:
            corpo_html = build_email_shell(
                f"Ticket {numero_chamado} — New Reply",
                "#0891b2",
                f"<p>The responsible <em>{escape(respondente_nome)}</em> replied to ticket "
                f"<strong>{escape(numero_chamado)}</strong> ({escape(categoria_en)}).</p>"
                + build_detail_table(
                    [
                        ("Ticket", numero_chamado),
                        ("Category", categoria_en),
                        ("Message", mensagem),
                        ("Replied by", respondente_nome),
                    ]
                )
                + (build_cta_button("View ticket", link, "#2563eb") if link else ""),
            )
            corpo_texto = (
                f"Ticket {numero_chamado} — new reply from {respondente_nome}.\n"
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
                tipo="resposta_responsavel",
                categoria=categoria,
            )
            webpush_service.enviar_webpush_usuario(
                uid,
                titulo=assunto,
                corpo=categoria,
                url=link or "",
            )


def _link_chamado(chamado_id: str) -> str:
    """Link "View ticket" usado em todos os e-mails deste módulo.

    Construído direto a partir de APP_BASE_URL (mesmo padrão de
    notifications_core.py/status_service.py), não com url_for(_external=True)
    dentro de um current_app.test_request_context() solto: sem SERVER_NAME
    configurado em lugar nenhum do app, esse context assume host "localhost"
    e ignora APP_BASE_URL por completo — todo e-mail deste módulo linkava pra
    http://localhost/... mesmo em produção (achado 2026-08-17).
    """
    try:
        from flask import current_app

        base = (current_app.config.get("APP_BASE_URL") or "").strip().rstrip("/")
        return f"{base}/chamado/{chamado_id}" if base else ""
    except Exception:
        return ""


def _link_decisao_previsao(solicitacao_id: int, acao: str) -> str:
    """Link assinado (token de uso único) pra decidir o pedido direto do e-mail —
    ver previsao_atendimento_service.gerar_token_decisao/validar_token_decisao.
    Construído a partir de APP_BASE_URL — ver _link_chamado acima pro porquê."""
    try:
        from flask import current_app

        from app.services.previsao_atendimento_service import gerar_token_decisao

        token = gerar_token_decisao(solicitacao_id, acao)
        base = (current_app.config.get("APP_BASE_URL") or "").strip().rstrip("/")
        return f"{base}/aprovacao-previsao/{token}" if base else ""
    except Exception:
        return ""


def notificar_solicitacao_previsao_atendimento(
    *,
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    solicitante_nome: str,
    previsao_solicitada,
    motivo: str,
    solicitacao_id: int,
    gestor_usuario,
) -> None:
    """Notifica o gestor decisor (gestor_setor da área do chamado, ou fallback —
    ver resolver_gestor_decisor) de um novo pedido de previsão de atendimento,
    com botões Aprovar/Rejeitar de um clique só (e-mail) + notificação in-app."""
    if gestor_usuario is None:
        logger.warning(
            "Solicitação de previsão CH %s: nenhum gestor decisor encontrado, "
            "notificação não enviada (pedido fica pendente até alguém decidir pelo sistema).",
            numero_chamado,
        )
        return

    link_aprovar = _link_decisao_previsao(solicitacao_id, "aprovar")
    link_rejeitar = _link_decisao_previsao(solicitacao_id, "rejeitar")
    link_chamado = _link_chamado(chamado_id)
    previsao_fmt = str(previsao_solicitada)

    email = getattr(gestor_usuario, "email", None)
    uid = getattr(gestor_usuario, "id", None)

    categoria_en = get_translated_category(categoria, "en")
    assunto = get_translation(
        "push_subject_previsao_solicitada", "en", numero=numero_chamado, categoria=categoria_en
    )

    if email:
        ctas = []
        if link_aprovar:
            ctas.append(("Approve", link_aprovar, "#16a34a"))
        if link_rejeitar:
            ctas.append(("Reject", link_rejeitar, "#dc2626"))
        corpo_html = build_email_shell(
            f"Ticket {numero_chamado} — Attendance Forecast Request",
            "#d97706",
            f"<p><em>{escape(solicitante_nome)}</em> requested a new attendance forecast for "
            f"ticket <strong>{escape(numero_chamado)}</strong> ({escape(categoria_en)}).</p>"
            + build_detail_table(
                [
                    ("Ticket", numero_chamado),
                    ("Category", categoria_en),
                    ("Requested date", previsao_fmt),
                    ("Reason", motivo),
                    ("Requested by", solicitante_nome),
                ]
            )
            + build_two_ctas(ctas)
            + (build_cta_button("View ticket", link_chamado, "#2563eb") if link_chamado else ""),
        )
        corpo_texto = (
            f"Ticket {numero_chamado} — {solicitante_nome} requested a new attendance forecast "
            f"({previsao_fmt}). Reason: {motivo}\n\nApprove: {link_aprovar}\nReject: {link_rejeitar}"
        )
        ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="high")
        if ok:
            logger.info(
                "Attendance forecast request e-mail sent to %s (ticket %s)", email, numero_chamado
            )
        else:
            logger.warning(
                "Failed to send attendance forecast request e-mail to %s (ticket %s): %s",
                email,
                numero_chamado,
                err,
            )

    if uid:
        criar_notificacao(
            usuario_id=uid,
            chamado_id=chamado_id,
            numero_chamado=numero_chamado,
            titulo=f"Previsão de atendimento pendente — Chamado {numero_chamado}",
            mensagem=categoria,
            tipo="previsao_atendimento_solicitada",
            categoria=categoria,
        )
        webpush_service.enviar_webpush_usuario(
            uid,
            titulo=assunto,
            corpo=categoria,
            url=link_chamado or "",
        )


def notificar_decisao_previsao_atendimento(
    *,
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    acao: str,
    previsao_solicitada,
    motivo_rejeicao: str | None,
    gestor_nome: str,
    solicitante_id: str,
) -> None:
    """Notifica quem PEDIU a previsão de atendimento (supervisor/admin owner do
    chamado — não o solicitante original do chamado, que nunca pode pedir isso,
    ver previsao_atendimento_service.solicitar_previsao_atendimento) da decisão
    do gestor — via inversa de notificar_solicitacao_previsao_atendimento."""
    solicitante = Usuario.get_by_id(solicitante_id) if solicitante_id else None
    destinatarios = [solicitante] if solicitante else []
    if not destinatarios:
        logger.info(
            "Decisão de previsão CH %s: solicitante %s não encontrado, no e-mail sent.",
            numero_chamado,
            solicitante_id,
        )
        return

    aprovado = acao == "aprovar"
    link = _link_chamado(chamado_id)
    previsao_fmt = str(previsao_solicitada)
    categoria_en = get_translated_category(categoria, "en")
    assunto = get_translation(
        "push_subject_previsao_decidida",
        "en",
        numero=numero_chamado,
        status="Approved" if aprovado else "Rejected",
    )

    for usuario in destinatarios:
        email = getattr(usuario, "email", None)
        uid = getattr(usuario, "id", None)

        if email:
            cor = "#16a34a" if aprovado else "#dc2626"
            detalhes = [
                ("Ticket", numero_chamado),
                ("Category", categoria_en),
                ("Requested date", previsao_fmt),
                ("Decided by", gestor_nome),
            ]
            if not aprovado and motivo_rejeicao:
                detalhes.append(("Rejection reason", motivo_rejeicao))
            corpo_html = build_email_shell(
                f"Ticket {numero_chamado} — Attendance Forecast "
                f"{'Approved' if aprovado else 'Rejected'}",
                cor,
                f"<p>Your attendance forecast request for ticket "
                f"<strong>{escape(numero_chamado)}</strong> was "
                f"<strong>{'approved' if aprovado else 'rejected'}</strong> by "
                f"<em>{escape(gestor_nome)}</em>.</p>"
                + build_detail_table(detalhes)
                + (build_cta_button("View ticket", link, "#2563eb") if link else ""),
            )
            corpo_texto = (
                f"Ticket {numero_chamado} — attendance forecast request "
                f"{'approved' if aprovado else 'rejected'} by {gestor_nome}."
                + (f"\nReason: {motivo_rejeicao}" if not aprovado and motivo_rejeicao else "")
                + (f"\n\nView ticket: {link}" if link else "")
            )
            ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="normal")
            if ok:
                logger.info(
                    "Attendance forecast decision e-mail sent to %s (ticket %s)",
                    email,
                    numero_chamado,
                )
            else:
                logger.warning(
                    "Failed to send attendance forecast decision e-mail to %s (ticket %s): %s",
                    email,
                    numero_chamado,
                    err,
                )

        if uid:
            criar_notificacao(
                usuario_id=uid,
                chamado_id=chamado_id,
                numero_chamado=numero_chamado,
                titulo=(
                    f"Previsão aprovada — Chamado {numero_chamado}"
                    if aprovado
                    else f"Previsão rejeitada — Chamado {numero_chamado}"
                ),
                mensagem=categoria,
                tipo=(
                    "previsao_atendimento_aprovada"
                    if aprovado
                    else "previsao_atendimento_rejeitada"
                ),
                categoria=categoria,
            )
            webpush_service.enviar_webpush_usuario(
                uid,
                titulo=assunto,
                corpo=categoria,
                url=link or "",
            )


def notificar_extensao_automatica_previsao(
    *,
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    previsao_nova,
    extensoes_usadas: int,
    extensoes_restantes: int,
    solicitante_id: str | None,
    responsavel_id: str,
    chamado_area: str,
) -> None:
    """Notifica os 4 papéis de uma extensão automática (self-service, sem
    aprovação do gestor) aplicada com sucesso: o solicitante do chamado, o
    gestor_setor do departamento do solicitante (resolver_gestor_do_solicitante
    — NÃO o mesmo lookup do gestor decisor), o gestor_setor da área que
    atende o chamado (resolver_gestor_decisor, igual ao fluxo manual), e o
    responsável que clicou — esse último com uma mensagem própria de
    confirmação, avisando quantas extensões automáticas ainda restam."""
    from app.services.previsao_atendimento_service import (
        resolver_gestor_decisor,
        resolver_gestor_do_solicitante,
    )

    solicitante_usuario = Usuario.get_by_id(solicitante_id) if solicitante_id else None
    responsavel_usuario = Usuario.get_by_id(responsavel_id) if responsavel_id else None
    gestor_solicitante = (
        resolver_gestor_do_solicitante(solicitante_usuario) if solicitante_usuario else None
    )
    gestor_solicitado = resolver_gestor_decisor(chamado_area or "")

    link = _link_chamado(chamado_id)
    previsao_fmt = str(previsao_nova)
    categoria_en = get_translated_category(categoria, "en")
    assunto = get_translation(
        "push_subject_previsao_extensao_automatica",
        "en",
        numero=numero_chamado,
        categoria=categoria_en,
    )
    detalhes = [
        ("Ticket", numero_chamado),
        ("Category", categoria_en),
        ("New deadline", previsao_fmt),
    ]

    vistos: set = set()

    for usuario in (solicitante_usuario, gestor_solicitante, gestor_solicitado):
        if usuario is None:
            continue
        uid = getattr(usuario, "id", None)
        if uid is None or uid in vistos:
            continue
        vistos.add(uid)

        email = getattr(usuario, "email", None)
        if email:
            corpo_html = build_email_shell(
                f"Ticket {numero_chamado} — Deadline Automatically Extended",
                "#d97706",
                f"<p>The deadline for ticket <strong>{escape(numero_chamado)}</strong> "
                f"({escape(categoria_en)}) was automatically extended to "
                f"<strong>{escape(previsao_fmt)}</strong> (self-service, no manager approval "
                "was needed for this extension).</p>"
                + build_detail_table(detalhes)
                + (build_cta_button("View ticket", link, "#2563eb") if link else ""),
            )
            corpo_texto = (
                f"Ticket {numero_chamado} — deadline automatically extended to {previsao_fmt}."
                + (f"\n\nView ticket: {link}" if link else "")
            )
            ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="normal")
            if ok:
                logger.info(
                    "Automatic extension e-mail sent to %s (ticket %s)", email, numero_chamado
                )
            else:
                logger.warning(
                    "Failed to send automatic extension e-mail to %s (ticket %s): %s",
                    email,
                    numero_chamado,
                    err,
                )

        if uid:
            criar_notificacao(
                usuario_id=uid,
                chamado_id=chamado_id,
                numero_chamado=numero_chamado,
                titulo=f"Prazo adiado automaticamente — Chamado {numero_chamado}",
                mensagem=categoria,
                tipo="previsao_extensao_automatica_aplicada",
                categoria=categoria,
            )
            webpush_service.enviar_webpush_usuario(
                uid,
                titulo=assunto,
                corpo=categoria,
                url=link or "",
            )

    # 5º papel: o responsável que clicou — mensagem própria com a contagem
    # de extensões restantes, não misturada no loop genérico acima.
    if responsavel_usuario is not None:
        uid = getattr(responsavel_usuario, "id", None)
        if uid not in vistos:
            email = getattr(responsavel_usuario, "email", None)
            if email:
                corpo_html = build_email_shell(
                    f"Ticket {numero_chamado} — Automatic Extension Applied",
                    "#16a34a",
                    f"<p>Your automatic extension for ticket "
                    f"<strong>{escape(numero_chamado)}</strong> was applied — new deadline "
                    f"<strong>{escape(previsao_fmt)}</strong>. You have "
                    f"<strong>{extensoes_restantes}</strong> automatic extension(s) left on "
                    "this ticket before a manager approval is required.</p>"
                    + build_detail_table(detalhes)
                    + (build_cta_button("View ticket", link, "#2563eb") if link else ""),
                )
                corpo_texto = (
                    f"Ticket {numero_chamado} — automatic extension applied, new deadline "
                    f"{previsao_fmt}. {extensoes_restantes} automatic extension(s) left."
                    + (f"\n\nView ticket: {link}" if link else "")
                )
                ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="normal")
                if ok:
                    logger.info(
                        "Automatic extension confirmation e-mail sent to %s (ticket %s)",
                        email,
                        numero_chamado,
                    )
                else:
                    logger.warning(
                        "Failed to send automatic extension confirmation e-mail to %s "
                        "(ticket %s): %s",
                        email,
                        numero_chamado,
                        err,
                    )

            if uid:
                criar_notificacao(
                    usuario_id=uid,
                    chamado_id=chamado_id,
                    numero_chamado=numero_chamado,
                    titulo=(
                        f"Extensão automática aplicada — restam {extensoes_restantes} "
                        f"de {extensoes_usadas + extensoes_restantes}"
                    ),
                    mensagem=categoria,
                    tipo="previsao_extensao_automatica_confirmacao",
                    categoria=categoria,
                )
                webpush_service.enviar_webpush_usuario(
                    uid,
                    titulo=assunto,
                    corpo=categoria,
                    url=link or "",
                )


# ── Helpers de disparo em thread (usados pelas rotas) ───────────────────────


def disparar_notificacao_solicitacao_previsao_em_thread(
    app,
    *,
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    solicitante_nome: str,
    previsao_solicitada,
    motivo: str,
    solicitacao_id: int,
    gestor_id: str | None,
) -> None:
    """Busca o Usuario do gestor e dispara notificar_solicitacao_previsao_atendimento
    em background — usado por api_colaboracao.api_solicitar_previsao_atendimento."""
    import threading

    def _run():
        with app.app_context():
            try:
                gestor_usuario = Usuario.get_by_id(gestor_id) if gestor_id else None
                notificar_solicitacao_previsao_atendimento(
                    chamado_id=chamado_id,
                    numero_chamado=numero_chamado,
                    categoria=categoria,
                    solicitante_nome=solicitante_nome,
                    previsao_solicitada=previsao_solicitada,
                    motivo=motivo,
                    solicitacao_id=solicitacao_id,
                    gestor_usuario=gestor_usuario,
                )
            except Exception as exc:
                logger.warning("Notificação de solicitação de previsão não enviada: %s", exc)

    threading.Thread(target=_run, daemon=True).start()


def disparar_notificacao_decisao_previsao_em_thread(
    app, resultado_dados: dict, gestor_nome: str
) -> None:
    """Busca numero_chamado/categoria do chamado e dispara
    notificar_decisao_previsao_atendimento em background — usado tanto pela
    decisão via sistema quanto pela decisão via link de e-mail
    (app/routes/aprovacao_previsao.py)."""
    import threading

    from app.models import Chamado

    chamado_id = resultado_dados["chamado_id"]
    chamado = Chamado.get_by_id(chamado_id)
    numero_chamado = chamado.numero_chamado if chamado else "N/A"
    categoria = chamado.categoria if chamado else ""

    def _run():
        with app.app_context():
            try:
                notificar_decisao_previsao_atendimento(
                    chamado_id=chamado_id,
                    numero_chamado=numero_chamado,
                    categoria=categoria,
                    acao=resultado_dados["acao"],
                    previsao_solicitada=resultado_dados["previsao_solicitada"],
                    motivo_rejeicao=resultado_dados.get("motivo_rejeicao"),
                    gestor_nome=gestor_nome,
                    solicitante_id=resultado_dados["solicitante_id"],
                )
            except Exception as exc:
                logger.warning("Notificação de decisão de previsão não enviada: %s", exc)

    threading.Thread(target=_run, daemon=True).start()


def disparar_notificacao_extensao_automatica_em_thread(
    app,
    *,
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    previsao_nova,
    extensoes_usadas: int,
    extensoes_restantes: int,
    solicitante_id: str | None,
    responsavel_id: str,
    chamado_area: str,
) -> None:
    """Dispara notificar_extensao_automatica_previsao em background — usado
    por api_colaboracao.api_solicitar_extensao_automatica_previsao."""
    import threading

    def _run():
        with app.app_context():
            try:
                notificar_extensao_automatica_previsao(
                    chamado_id=chamado_id,
                    numero_chamado=numero_chamado,
                    categoria=categoria,
                    previsao_nova=previsao_nova,
                    extensoes_usadas=extensoes_usadas,
                    extensoes_restantes=extensoes_restantes,
                    solicitante_id=solicitante_id,
                    responsavel_id=responsavel_id,
                    chamado_area=chamado_area,
                )
            except Exception as exc:
                logger.warning("Notificação de extensão automática não enviada: %s", exc)

    threading.Thread(target=_run, daemon=True).start()
