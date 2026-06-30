"""
Fan-out centralizado de notificações de chamado.

  destinatarios_do_chamado(dados) → [Usuario, ...] (responsável + observadores)
  notificar_cancelamento_chamado(...)  → envia email a todos os destinatários
"""

import logging

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
        logger.info("Cancelamento CH %s: sem destinatários, nenhum e-mail enviado.", numero_chamado)
        return

    assunto = f"[Cancelado] Chamado {numero_chamado} — {categoria}"
    link = _link_chamado(chamado_id)

    for usuario in destinatarios:
        email = getattr(usuario, "email", None)
        uid = getattr(usuario, "id", None)

        if email:
            corpo_html = build_email_shell(
                f"Chamado {numero_chamado} Cancelado",
                "#dc2626",
                f"<p>O chamado <strong>{numero_chamado}</strong> foi <strong>cancelado</strong>"
                f" pelo solicitante <em>{solicitante_nome}</em>.</p>"
                + build_detail_table(
                    [
                        ("Chamado", numero_chamado),
                        ("Categoria", categoria),
                        ("Motivo", motivo),
                        ("Cancelado por", solicitante_nome),
                    ]
                )
                + (build_cta_button("Ver Chamado", link, "#2563eb") if link else ""),
            )
            corpo_texto = (
                f"Chamado {numero_chamado} cancelado por {solicitante_nome}.\n"
                f"Motivo: {motivo}\nCategoria: {categoria}"
                + (f"\n\nVer chamado: {link}" if link else "")
            )
            ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="normal")
            if ok:
                logger.info(
                    "Cancelamento email enviado para %s (chamado %s)", email, numero_chamado
                )
            else:
                logger.warning(
                    "Falha ao enviar cancelamento para %s (chamado %s): %s",
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
        logger.info(
            "Edição descrição CH %s: sem destinatários, nenhum e-mail enviado.", numero_chamado
        )
        return

    assunto = f"[Atualizado] Chamado {numero_chamado} — descrição editada"
    link = _link_chamado(chamado_id)
    _max_chars = 300

    anterior_trunc = (valor_anterior or "")[:_max_chars]
    novo_trunc = (valor_novo or "")[:_max_chars]

    for usuario in destinatarios:
        email = getattr(usuario, "email", None)
        uid = getattr(usuario, "id", None)

        if email:
            corpo_html = build_email_shell(
                f"Chamado {numero_chamado} — Descrição Editada",
                "#2563eb",
                f"<p>O solicitante <em>{solicitante_nome}</em> editou a descrição do chamado "
                f"<strong>{numero_chamado}</strong> ({categoria}).</p>"
                + build_detail_table(
                    [
                        ("Chamado", numero_chamado),
                        ("Categoria", categoria),
                        ("Editado por", solicitante_nome),
                        ("Descrição anterior", anterior_trunc),
                        ("Nova descrição", novo_trunc),
                    ]
                )
                + (build_cta_button("Ver Chamado", link, "#2563eb") if link else ""),
            )
            corpo_texto = (
                f"Chamado {numero_chamado} — descrição editada por {solicitante_nome}.\n"
                f"Anterior: {anterior_trunc}\nNovo: {novo_trunc}"
                + (f"\n\nVer chamado: {link}" if link else "")
            )
            ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="normal")
            if ok:
                logger.info(
                    "Edição descrição email enviado para %s (chamado %s)", email, numero_chamado
                )
            else:
                logger.warning(
                    "Falha ao enviar edição descrição para %s (chamado %s): %s",
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

    assunto = f"[Em cópia] Chamado {numero_chamado} — {categoria}"
    link = _link_chamado(chamado_id)

    for obs in observadores:
        email = obs.get("email") if isinstance(obs, dict) else getattr(obs, "email", None)
        nome = obs.get("nome") if isinstance(obs, dict) else getattr(obs, "nome", None)
        uid = obs.get("usuario_id") if isinstance(obs, dict) else getattr(obs, "usuario_id", None)

        if email:
            corpo_html = build_email_shell(
                f"Chamado {numero_chamado} — Você é observador",
                "#7c3aed",
                f"<p>Olá{f' {nome}' if nome else ''},</p>"
                f"<p>Você foi adicionado como <strong>observador</strong> do chamado "
                f"<strong>{numero_chamado}</strong> ({categoria}) aberto por "
                f"<em>{solicitante_nome}</em>.</p>"
                "<p>Você receberá notificações das atualizações deste chamado.</p>"
                + build_detail_table(
                    [
                        ("Chamado", numero_chamado),
                        ("Categoria", categoria),
                        ("Aberto por", solicitante_nome),
                    ]
                )
                + (build_cta_button("Ver Chamado", link, "#2563eb") if link else ""),
            )
            corpo_texto = (
                f"Você foi adicionado como observador do chamado {numero_chamado} ({categoria})"
                f" aberto por {solicitante_nome}." + (f"\n\nVer chamado: {link}" if link else "")
            )
            ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="normal")
            if ok:
                logger.info(
                    "Inclusão observador email enviado para %s (chamado %s)", email, numero_chamado
                )
            else:
                logger.warning(
                    "Falha ao enviar inclusão observador para %s (chamado %s): %s",
                    email,
                    numero_chamado,
                    err,
                )

        if uid:
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
            "Status %s CH %s: sem destinatários, nenhuma notificação enviada.",
            novo_status,
            numero_chamado,
        )
        return

    assunto = f"[{novo_status}] Chamado {numero_chamado} — {categoria}"
    link = _link_chamado(chamado_id)

    for usuario in destinatarios:
        email = getattr(usuario, "email", None)
        uid = getattr(usuario, "id", None)

        if email:
            corpo_html = build_email_shell(
                f"Chamado {numero_chamado}: {novo_status}",
                "#2563eb",
                f"<p>O status do chamado <strong>{numero_chamado}</strong> ({categoria}) "
                f"foi atualizado para <strong>{novo_status}</strong>.</p>"
                + build_detail_table(
                    [
                        ("Chamado", numero_chamado),
                        ("Categoria", categoria),
                        ("Novo status", novo_status),
                    ]
                )
                + (build_cta_button("Ver Chamado", link, "#2563eb") if link else ""),
            )
            corpo_texto = f"Chamado {numero_chamado} — status atualizado para {novo_status}." + (
                f"\n\nVer chamado: {link}" if link else ""
            )
            ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="normal")
            if ok:
                logger.info(
                    "Status %s email enviado para %s (chamado %s)",
                    novo_status,
                    email,
                    numero_chamado,
                )
            else:
                logger.warning(
                    "Falha ao enviar status %s para %s (chamado %s): %s",
                    novo_status,
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
        logger.info("Anexo tardio CH %s: sem destinatários, nenhum e-mail enviado.", numero_chamado)
        return

    assunto = f"[Anexo] Chamado {numero_chamado} — novo documento adicionado"
    link = _link_chamado(chamado_id)

    for usuario in destinatarios:
        email = getattr(usuario, "email", None)
        uid = getattr(usuario, "id", None)

        if email:
            corpo_html = build_email_shell(
                f"Chamado {numero_chamado} — Novo Anexo",
                "#0891b2",
                f"<p>O solicitante <em>{solicitante_nome}</em> adicionou um novo anexo ao chamado "
                f"<strong>{numero_chamado}</strong> ({categoria}).</p>"
                + build_detail_table(
                    [
                        ("Chamado", numero_chamado),
                        ("Categoria", categoria),
                        ("Arquivo", nome_arquivo),
                        ("Motivo", motivo),
                        ("Adicionado por", solicitante_nome),
                    ]
                )
                + (build_cta_button("Ver Chamado", link, "#2563eb") if link else ""),
            )
            corpo_texto = (
                f"Chamado {numero_chamado} — novo anexo adicionado por {solicitante_nome}.\n"
                f"Arquivo: {nome_arquivo}\nMotivo: {motivo}"
                + (f"\n\nVer chamado: {link}" if link else "")
            )
            ok, err = enviar_email(email, assunto, corpo_html, corpo_texto, importance="normal")
            if ok:
                logger.info(
                    "Anexo tardio email enviado para %s (chamado %s)", email, numero_chamado
                )
            else:
                logger.warning(
                    "Falha ao enviar anexo tardio para %s (chamado %s): %s",
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


def _link_chamado(chamado_id: str) -> str:
    try:
        from flask import current_app, url_for

        with current_app.test_request_context():
            return url_for("main.visualizar_chamado", chamado_id=chamado_id, _external=True)
    except Exception:
        return ""
