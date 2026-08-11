"""Notificações de escalonamento gerencial: motor unificado (TAT por
categoria), aviso prévio ao responsável, AOG, digest diário."""

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

NOMES_NIVEL: dict[int, str] = {
    1: "Sector Manager",
    2: "Production Manager",
    3: "GM Assistant",
    4: "GM",
}


def notificar_escalada_gerencial(
    chamado_data: dict,
    chamado_id: str,
    nivel: int,
    email_dest: str,
    assumido: bool,
) -> None:
    """Notifica gestor que um chamado excedeu o TAT (motor de escalonamento
    unificado — ver app/services/sla_escalacao_service.py).

    `assumido` indica se o chamado já está "Em Atendimento" no momento deste
    tick (True) ou ainda "Aberto"/não reivindicado (False) — muda só o texto
    do e-mail, o canal e o nível são os mesmos.
    """
    numero_chamado = chamado_data.get("numero_chamado") or "N/A"
    categoria = chamado_data.get("categoria") or ""
    area = chamado_data.get("area") or ""
    tipo_solicitacao = chamado_data.get("tipo_solicitacao") or ""
    descricao_resumo = (chamado_data.get("descricao") or "")[:500]
    cat_d = _tc(categoria)
    area_d = _ts(area)
    tipo_d = _ts(tipo_solicitacao)

    nome_nivel = NOMES_NIVEL.get(nivel, f"Level {nivel}")

    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()

    situacao = "resolution overdue" if assumido else "not claimed"
    assunto = f"[SLA Alert] Ticket {numero_chamado} — {situacao} (Level {nivel})"

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

    if assumido:
        frase = (
            f"<p>Ticket <strong>{escape(numero_chamado)}</strong> is overdue for resolution. "
            f"This notification is addressed to the <strong>{nome_nivel}</strong>.</p>"
        )
        titulo = f"SLA Alert — Ticket {escape(numero_chamado)} resolution overdue"
    else:
        frase = (
            f"<p>Ticket <strong>{escape(numero_chamado)}</strong> has not been claimed yet. "
            f"This notification is addressed to the <strong>{nome_nivel}</strong>.</p>"
        )
        titulo = f"SLA Alert — Ticket {escape(numero_chamado)} not claimed"

    corpo_html = build_email_shell(
        header_title=titulo,
        header_color="#dc2626",
        body_html=frase + detalhes_html + summary_html + botoes_html,
    )
    corpo_texto = (
        f"SLA Alert — Ticket {numero_chamado} {situacao}.\n"
        f"Escalation Level {nivel} ({nome_nivel}).\n"
        f"Category: {cat_d}\nArea: {area_d}" + (f"\n\nView ticket: {link}" if link else "")
    )

    ok, err = enviar_email(
        email_dest,
        assunto,
        corpo_html,
        corpo_texto,
        importance=resolver_importance("escalada_gerencial"),
    )
    if ok:
        logger.info(
            "SLA escalation (level %d) sent to %s (ticket %s)", nivel, email_dest, numero_chamado
        )
    else:
        logger.warning("Failed to send SLA escalation notification to %s: %s", email_dest, err)


def notificar_pre_aviso_escalonamento(
    chamado_data: dict,
    chamado_id: str,
    nivel_alvo: int,
    minutos_restantes: int,
    responsavel_id: str | None,
    email_dest: str | None,
) -> None:
    """Avisa o responsável, ~SLA_PRE_AVISO_MINUTOS antes, que este chamado
    específico vai escalar para o próximo nível de gestão em breve.

    Só sobre este chamado (não uma lista de vários) — ver
    app/services/digest_diario_service.py pro resumo diário geral. Canais:
    in-app + Web Push (quando responsavel_id) + e-mail (quando email_dest),
    cada um independente (falha em um não bloqueia os outros).
    """
    numero_chamado = chamado_data.get("numero_chamado") or "N/A"
    categoria = chamado_data.get("categoria") or ""
    area = chamado_data.get("area") or ""
    tipo_solicitacao = chamado_data.get("tipo_solicitacao") or ""
    cat_d = _tc(categoria)
    area_d = _ts(area)
    tipo_d = _ts(tipo_solicitacao)
    nome_nivel = NOMES_NIVEL.get(nivel_alvo, f"Level {nivel_alvo}")

    link = _link_chamado(chamado_id)
    assunto = f"[Heads up] Ticket {numero_chamado} will escalate in {minutos_restantes} min"
    mensagem_curta = (
        f"Ticket {numero_chamado} will escalate to the {nome_nivel} "
        f"in about {minutos_restantes} minutes if it's not handled."
    )

    if responsavel_id:
        try:
            from app.services.notifications_inapp import criar_notificacao

            criar_notificacao(
                usuario_id=responsavel_id,
                chamado_id=chamado_id,
                numero_chamado=numero_chamado,
                titulo=assunto,
                mensagem=mensagem_curta,
                tipo="pre_aviso_escalonamento",
                categoria=categoria,
            )
        except Exception as exc:
            logger.warning("In-app pre-warning failed (ticket %s): %s", chamado_id, exc)

        try:
            from app.services.webpush_service import enviar_webpush_usuario

            enviar_webpush_usuario(
                usuario_id=responsavel_id,
                titulo=assunto,
                corpo=mensagem_curta,
                url=link or None,
            )
        except Exception as exc:
            logger.warning("WebPush pre-warning failed (ticket %s): %s", chamado_id, exc)

    if not email_dest:
        return

    detalhes_html = build_detail_table(
        [
            ("Number", numero_chamado),
            ("Category", cat_d),
            ("Type", tipo_d),
            ("Area", area_d),
            ("Will escalate to", f"{nivel_alvo} — {nome_nivel}"),
            ("Time remaining", f"~{minutos_restantes} minutes"),
        ]
    )
    ctas = [("View ticket", link, "#d97706")] if link else []
    botoes_html = build_two_ctas(ctas) if ctas else ""

    corpo_html = build_email_shell(
        header_title=f"Heads up — Ticket {escape(numero_chamado)} about to escalate",
        header_color="#d97706",
        body_html=(f"<p>{escape(mensagem_curta)}</p>" + detalhes_html + botoes_html),
    )
    corpo_texto = f"{mensagem_curta}\nCategory: {cat_d}\nArea: {area_d}" + (
        f"\n\nView ticket: {link}" if link else ""
    )

    ok, err = enviar_email(
        email_dest,
        assunto,
        corpo_html,
        corpo_texto,
        importance=resolver_importance("pre_aviso_escalonamento"),
    )
    if ok:
        logger.info("Pre-warning sent to %s (ticket %s)", email_dest, numero_chamado)
    else:
        logger.warning("Failed to send pre-warning to %s: %s", email_dest, err)


_AOG_BROADCAST_CACHE_KEY = "aog_broadcast_usuarios"


def notificar_abertura_aog_todos_gestores(
    chamado_data: dict, chamado_id: str, solicitante_id: str | None = None
) -> None:
    """Notifica TODO usuário ativo do sistema, exceto quem abriu o chamado,
    simultaneamente na abertura de um chamado AOG.

    AOG (Aircraft On Ground) é emergência imediata e prioridade máxima —
    avisa todo mundo de uma vez na abertura, sem esperar o job de
    escalonamento nem a janela de expediente. Os 4 níveis de gestão
    recebem o mesmo e-mail, como qualquer outro usuário ativo — não há
    tratamento diferenciado pra eles aqui (o cadastro de nivel_gestao só
    importa pro motor de escalonamento gradual, não pra este broadcast).

    Usa cache próprio (chave distinta de "sla_gestores_usuarios"/
    "usuarios_all" usadas em outros lugares) pra não ler a tabela inteira de
    usuários a cada AOG aberto.
    """
    from app.cache import get_static_cached
    from app.models_usuario import Usuario

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
            "This notification was sent to everyone in the system at once.</p>"
            + detalhes_html
            + summary_html
            + botoes_html
        ),
    )
    corpo_texto = (
        f"AOG — Ticket {numero_chamado} needs immediate attention.\n"
        f"Category: {cat_d}\nArea: {area_d}" + (f"\n\nView ticket: {link}" if link else "")
    )

    importance = resolver_importance("abertura_aog")

    try:
        usuarios = get_static_cached(_AOG_BROADCAST_CACHE_KEY, Usuario.get_all, ttl_seconds=300)
    except Exception as exc:
        logger.exception("AOG abertura: falha ao listar usuários pro broadcast: %s", exc)
        return

    destinatarios: set[str] = set()
    for usuario in usuarios:
        if not getattr(usuario, "ativo", True):
            continue
        if solicitante_id and getattr(usuario, "id", None) == solicitante_id:
            continue
        email = (getattr(usuario, "email", None) or "").strip()
        if email:
            destinatarios.add(email)

    if not destinatarios:
        logger.warning(
            "AOG abertura: nenhum destinatário ativo encontrado pro broadcast (chamado %s).",
            numero_chamado,
        )
        return

    for email_dest in sorted(destinatarios):
        try:
            ok, err = enviar_email(
                email_dest, assunto, corpo_html, corpo_texto, importance=importance
            )
            if not ok:
                logger.warning(
                    "AOG abertura: falha ao enviar pra %s (chamado %s): %s",
                    email_dest,
                    numero_chamado,
                    err,
                )
        except Exception as exc:
            logger.warning(
                "AOG abertura: exceção ao notificar %s (chamado %s): %s",
                email_dest,
                numero_chamado,
                exc,
            )

    logger.info(
        "AOG abertura: broadcast enviado pra %d destinatário(s) (chamado %s)",
        len(destinatarios),
        numero_chamado,
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


# ---------------------------------------------------------------------------
# Digest diário — resumo geral (não sobre um chamado específico, ver
# app/services/digest_diario_service.py pro gatilho/agrupamento).
# ---------------------------------------------------------------------------


def _linha_digest(item: dict) -> str:
    numero = item.get("numero_chamado") or "N/A"
    link = _link_chamado(item.get("id"))
    numero_html = (
        f'<a href="{escape(link)}" style="color:#2563eb;text-decoration:none;">{escape(numero)}</a>'
        if link
        else escape(numero)
    )
    cat_d = escape(_tc(item.get("categoria") or ""))
    status_d = escape(item.get("status") or "")
    return (
        "<tr>"
        f'<td style="padding:8px 12px;border-top:1px solid #e5e7eb;">{numero_html}</td>'
        f'<td style="padding:8px 12px;border-top:1px solid #e5e7eb;">{cat_d}</td>'
        f'<td style="padding:8px 12px;border-top:1px solid #e5e7eb;">{status_d}</td>'
        "</tr>"
    )


def _tabela_digest(itens: list[dict]) -> str:
    if not itens:
        return '<p style="color:#6b7280;margin:4px 0 16px;">None.</p>'
    linhas = "".join(_linha_digest(item) for item in itens)
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="margin:4px 0 16px;border:1px solid #e5e7eb;border-radius:8px;'
        'border-collapse:collapse;overflow:hidden;">'
        '<tr style="background:#f9fafb;">'
        '<td style="padding:8px 12px;"><strong>Ticket</strong></td>'
        '<td style="padding:8px 12px;"><strong>Category</strong></td>'
        '<td style="padding:8px 12px;"><strong>Status</strong></td>'
        "</tr>" + linhas + "</table>"
    )


def notificar_digest_diario(
    usuario_id: str,
    email_dest: str,
    vencidos_ou_perto: list[dict],
    abertos: list[dict],
) -> None:
    """E-mail diário-resumo de TODOS os chamados abertos/em atendimento de um
    responsável, agrupados em "Overdue / near deadline" e "Open" — cada grupo
    já vem ordenado por prioridade de categoria (AOG > Projetos > demais) e
    urgência, feito por quem monta as listas (digest_diario_service.py).

    Diferente do aviso prévio (notificar_pre_aviso_escalonamento, sobre 1
    chamado específico prestes a escalar), este é uma visão geral periódica —
    as duas coexistem. Inglês hardcoded, mesmo padrão dos demais e-mails
    desta família.
    """
    link_dash = _link_dashboard()
    link_meus_pendentes = f"{link_dash}?meus_pendentes=1" if link_dash else ""
    total = len(vencidos_ou_perto) + len(abertos)

    assunto = f"[Daily digest] {total} open ticket(s) assigned to you"

    corpo_html = build_email_shell(
        header_title="Your open tickets — daily summary",
        header_color="#2563eb",
        body_html=(
            "<p>Here is a summary of every ticket currently open or in progress "
            "that is assigned to you.</p>"
            '<h3 style="margin:16px 0 4px;color:#dc2626;">Overdue / near deadline</h3>'
            + _tabela_digest(vencidos_ou_perto)
            + '<h3 style="margin:16px 0 4px;">Open</h3>'
            + _tabela_digest(abertos)
            + (
                build_two_ctas([("Open system", link_meus_pendentes, "#2563eb")])
                if link_meus_pendentes
                else ""
            )
        ),
    )
    corpo_texto = f"Daily digest: {total} open ticket(s) assigned to you."

    ok, err = enviar_email(
        email_dest,
        assunto,
        corpo_html,
        corpo_texto,
        importance=resolver_importance("digest_diario"),
    )
    if ok:
        logger.info("Digest diário enviado pra %s (usuário %s)", email_dest, usuario_id)
    else:
        logger.warning("Falha ao enviar digest diário pra %s: %s", email_dest, err)
