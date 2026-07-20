"""Notificações de escalonamento gerencial: SLA de resposta (Escada A), AOG, SLA de resolução (Escada B)."""

import logging
from html import escape

from app.services.email_templates import build_detail_table, build_email_shell, build_two_ctas
from app.services.notifications_core import (
    _link_chamado,
    _link_dashboard,
    _tc,
    _ts,
    enviar_email,
    resolver_importance,
)

logger = logging.getLogger(__name__)


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

    ok, err = enviar_email(
        email_dest,
        assunto,
        corpo_html,
        corpo_texto,
        importance=resolver_importance("escalada_resposta_gerencial"),
    )
    if ok:
        logger.info(
            "SLA escalation (level %d) sent to %s (ticket %s)", nivel, email_dest, numero_chamado
        )
    else:
        logger.warning("Failed to send SLA escalation notification to %s: %s", email_dest, err)


_NIVEIS_GESTOR_AOG: tuple[str, ...] = ("gestor_setor", "gerente_producao", "assistente_gm", "gm")


def notificar_abertura_aog_todos_gestores(chamado_data: dict, chamado_id: str) -> None:
    """Notifica os 4 níveis de gestão simultaneamente na abertura de um chamado AOG.

    Diferente da Escada A normal (escalada gradual, 1 nível por vez conforme o tempo
    passa), AOG (Aircraft On Ground) é emergência imediata — avisa todo mundo de uma
    vez na abertura, sem esperar o job de escalonamento nem a janela de expediente.
    gestor_setor é resolvido pela área/categoria do próprio chamado, igual à
    Escada A/B. Nível sem ninguém cadastrado cascateia pro nível de gestão
    acima (nunca fica sem notificar por lacuna de cadastro — é emergência);
    se a cascata leva dois níveis pro mesmo destinatário, notifica só uma vez.
    Só fica sem notificar se NENHUM nível tiver alguém cadastrado (log warning).
    """
    from app.services.gestor_escalonamento_service import (
        construir_mapa_gestor_setor,
        construir_mapa_niveis_superiores,
        resolver_email_gestor_com_cascata,
    )

    numero_chamado = chamado_data.get("numero_chamado") or "N/A"
    categoria = chamado_data.get("categoria") or ""
    area = chamado_data.get("area") or ""
    tipo_solicitacao = chamado_data.get("tipo_solicitacao") or ""
    descricao_resumo = (chamado_data.get("descricao") or "")[:500]
    cat_d = _tc(categoria)
    area_d = _ts(area)
    tipo_d = _ts(tipo_solicitacao)

    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()

    assunto = f"[AOG] Ticket {numero_chamado} — aircraft on ground, immediate action required"

    detalhes_html = build_detail_table(
        [
            ("Number", numero_chamado),
            ("Category", cat_d),
            ("Type", tipo_d),
            ("Area", area_d),
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
        header_title=f"AOG — Ticket {escape(numero_chamado)} needs immediate attention",
        header_color="#dc2626",
        body_html=(
            "<p>An <strong>Aircraft On Ground (AOG)</strong> ticket was just opened. "
            "This notification was sent to all management levels at once.</p>"
            + detalhes_html
            + summary_html
            + botoes_html
        ),
    )
    corpo_texto = (
        f"AOG — Ticket {numero_chamado} needs immediate attention.\n"
        f"Category: {cat_d}\nArea: {area_d}" + (f"\n\nView ticket: {link}" if link else "")
    )

    mapa_gestor_setor = construir_mapa_gestor_setor()
    mapa_niveis_superiores = construir_mapa_niveis_superiores()

    importance = resolver_importance("abertura_aog")
    emails_ja_notificados: set[str] = set()
    for chave_gestor in _NIVEIS_GESTOR_AOG:
        email_dest = resolver_email_gestor_com_cascata(
            chave_gestor, categoria, mapa_gestor_setor, mapa_niveis_superiores
        )
        if not email_dest:
            logger.warning(
                "AOG abertura: nenhum usuário ativo com nivel_gestao='%s' (ou acima) "
                "cadastrado (chamado %s).",
                chave_gestor,
                numero_chamado,
            )
            continue
        if email_dest in emails_ja_notificados:
            logger.info(
                "AOG abertura: nível '%s' cascateou pro mesmo destinatário já notificado "
                "(%s, chamado %s) — não duplicado.",
                chave_gestor,
                email_dest,
                numero_chamado,
            )
            continue
        emails_ja_notificados.add(email_dest)
        try:
            ok, err = enviar_email(
                email_dest, assunto, corpo_html, corpo_texto, importance=importance
            )
            if ok:
                logger.info(
                    "AOG abertura: e-mail enviado pro nível '%s' (%s), chamado %s",
                    chave_gestor,
                    email_dest,
                    numero_chamado,
                )
            else:
                logger.warning(
                    "AOG abertura: falha ao enviar pro nível '%s' (%s): %s",
                    chave_gestor,
                    email_dest,
                    err,
                )
        except Exception as exc:
            logger.warning(
                "AOG abertura: exceção ao notificar nível '%s' (%s): %s",
                chave_gestor,
                email_dest,
                exc,
            )


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
        ok, err = enviar_email(
            email_dest,
            assunto,
            corpo_html,
            corpo_texto,
            importance=resolver_importance("aviso_resolucao_supervisor", marco_sla=marco),
        )
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

    ok, err = enviar_email(
        email_dest,
        assunto,
        corpo_html,
        corpo_texto,
        importance=resolver_importance("escalada_resolucao_gerencial"),
    )
    if ok:
        logger.info(
            "SLA resolution escalation (level %d) sent to %s (ticket %s)",
            nivel,
            email_dest,
            numero_chamado,
        )
    else:
        logger.warning("Failed to send SLA resolution escalation to %s: %s", email_dest, err)
