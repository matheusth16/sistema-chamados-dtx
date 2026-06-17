"""
Serviço de Notificações: E-mail via Microsoft Graph API (client credentials).

- Aprovador (responsável): notificado na criação do chamado.
- Solicitante: notificado em mudança de status (opt-in via NOTIFY_SOLICITANTE_EMAIL).
- Power Automate: relay via assunto estruturado (PREFIXO|ID|EMAIL).

Variáveis de ambiente obrigatórias:
  GRAPH_TENANT_ID     — Directory (tenant) ID do Azure AD
  GRAPH_CLIENT_ID     — Application (client) ID
  GRAPH_CLIENT_SECRET — Client secret value
  GRAPH_SENDER_EMAIL  — Caixa de envio (ex: dtxls.support@dtx.aero)
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

PREFIXO_ASSUNTO_CHAMADO_PRAZO_24H = "CHAMADO_PRAZO_24H"
PREFIXO_ASSUNTO_USUARIO_CADASTRADO = "USUARIO_CADASTRADO"
PREFIXO_ASSUNTO_CHAMADO_SETOR_ADICIONAL = "CHAMADO_SETOR_ADICIONAL"


def _sanitize_pa_field(value: str) -> str:
    """
    Remove o caractere '|' de campos usados no assunto do Power Automate.

    O assunto usa o formato PREFIXO|IDENTIFICADOR|EMAIL para roteamento.
    Se um campo contiver '|', o Power Automate parseia incorretamente o destinatário.
    """
    return str(value or "").replace("|", "-")


def _config(key: str, default=None):
    """Lê valor do Flask config via .get() (suporte correto a dict). Retorna default se fora de app context."""
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
    """
    Envia e-mail via Microsoft Graph API usando client credentials (sem SMTP).

    Fluxo:
    1. POST /oauth2/v2.0/token → obtém access_token
    2. POST /v1.0/users/{sender}/sendMail → envia mensagem
    """
    import json

    tenant_id = os.getenv("GRAPH_TENANT_ID", "").strip()
    client_id = os.getenv("GRAPH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GRAPH_CLIENT_SECRET", "").strip()
    sender_email = os.getenv("GRAPH_SENDER_EMAIL", "").strip() or from_addr.strip()

    if not all([tenant_id, client_id, client_secret, sender_email]):
        return (
            False,
            "Configuração incompleta: defina GRAPH_TENANT_ID, GRAPH_CLIENT_ID, "
            "GRAPH_CLIENT_SECRET e GRAPH_SENDER_EMAIL",
        )

    # 1. Obter token OAuth2 (client credentials)
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
        with urllib.request.urlopen(req_token, timeout=10) as resp:  # nosec B310 — URL constante HTTPS
            token_resp = json.loads(resp.read().decode("utf-8"))
            access_token = token_resp.get("access_token")
            if not access_token:
                err = f"Token não obtido da resposta Graph: {list(token_resp.keys())}"
                logger.warning(err)
                return (False, err)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        err = f"Graph token HTTP {e.code}: {body}"
        logger.warning("Falha ao obter token Graph: %s", err)
        return (False, err)
    except Exception as e:
        logger.exception("Falha ao obter token Graph para %s: %s", destinatario, e)
        return (False, f"Falha ao obter token OAuth2: {e}")

    # 2. Enviar e-mail via Graph sendMail
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
                logger.info("E-mail enviado via Graph para %s: %s", destinatario, assunto[:50])
                return (True, None)
            err = f"Graph sendMail status inesperado: {resp.status}"
            logger.warning(err)
            return (False, err)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        err = f"Graph sendMail HTTP {e.code}: {body}"
        logger.warning("Falha Graph sendMail para %s: %s", destinatario, err)
        return (False, err)
    except Exception as e:
        logger.exception("Falha ao enviar via Graph para %s: %s", destinatario, e)
        return (False, str(e))


def enviar_email(destinatario: str, assunto: str, corpo_html: str, corpo_texto: str = None):
    """
    Envia e-mail via Microsoft Graph API.
    Retorna (True, None) em sucesso ou (False, erro) em falha.
    """
    if not destinatario or not destinatario.strip():
        logger.warning("Notificação por e-mail ignorada: destinatário vazio")
        return (False, None)
    destinatario = destinatario.strip()

    from_addr = os.getenv("GRAPH_SENDER_EMAIL", "").strip() or "noreply@localhost"

    return _enviar_via_graph(destinatario, assunto, corpo_html, corpo_texto, from_addr)


def _base_url() -> str:
    """URL base da aplicação (para links em e-mails). Usa Flask config, .env ou request."""
    base = (_config("APP_BASE_URL") or os.getenv("APP_BASE_URL") or "").strip()
    if not base:
        try:
            if request and getattr(request, "url_root", None):
                base = request.url_root.rstrip("/")
        except RuntimeError:
            pass
    return base.rstrip("/") if base else ""


def _link_chamado(chamado_id: str) -> str:
    """URL para visualizar o chamado (histórico)."""
    base = _base_url()
    return f"{base}/chamado/{chamado_id}/historico" if base else ""


def _link_dashboard() -> str:
    """URL do painel (admin/supervisor ou index)."""
    base = _base_url()
    return f"{base}/admin" if base else ""


def _relay_email() -> str:
    """E-mail relay monitorado pelo Power Automate."""
    return (
        _config("NOTIFY_RELAY_EMAIL") or os.getenv("NOTIFY_RELAY_EMAIL", "dtxls.support@dtx.aero")
    ).strip()


def _disparar_evento_power_automate(
    prefixo_assunto: str,
    identificador: str,
    email_destino_final: str,
    corpo_html: str,
    corpo_texto: str,
):
    """
    Envia evento para o relay do Power Automate usando assunto estruturado.
    Formato: PREFIXO|IDENTIFICADOR|EMAIL_DESTINO
    """
    relay_email = _relay_email()
    assunto = f"{prefixo_assunto}|{_sanitize_pa_field(identificador)}|{_sanitize_pa_field(email_destino_final)}"
    current_app.logger.info(
        "Notificação por e-mail: enviando gatilho '%s' para Power Automate em %s",
        prefixo_assunto,
        relay_email,
    )
    ok, err = enviar_email(relay_email, assunto, corpo_html, corpo_texto)
    if ok:
        current_app.logger.info(
            "E-mail gatilho (%s) enviado com sucesso para %s",
            prefixo_assunto,
            relay_email,
        )
    else:
        current_app.logger.warning(
            "Falha ao enviar e-mail gatilho (%s) para %s: %s",
            prefixo_assunto,
            relay_email,
            err or "verifique MAIL_* e logs",
        )


# ---------- Notificação para APROVADOR (responsável) - Novo chamado ----------


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
    """
    Notifica o responsável (aprovador) que um novo chamado foi atribuído a ele.
    Envia e-mail via SMTP.
    """
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()

    if responsavel_usuario and getattr(responsavel_usuario, "email", None):
        # E-mail gatilho para Power Automate / Outlook (Delegated)
        relay_email = _relay_email()
        assunto = f"CHAMADO_NOVO|{_sanitize_pa_field(numero_chamado)}|{_sanitize_pa_field(responsavel_usuario.email)}"
        resumo_truncado = descricao_resumo[:500] + ("..." if len(descricao_resumo) > 500 else "")
        solicitante_linha = solicitante_nome
        if solicitante_email and solicitante_email.strip():
            solicitante_linha += f" ({solicitante_email.strip()})"
        corpo_texto = (
            f"Number: {numero_chamado}\n"
            f"Category: {categoria}\n"
            f"Type: {tipo_solicitacao}\n"
            f"Area: {area}\n"
            f"Requester: {solicitante_linha}\n"
            f"Summary: {resumo_truncado}\n\n"
            "Use the buttons in the email to access: View ticket history or View your sector tickets."
        )
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
            ctas.append(("View your sector tickets", link_dash, "#6b7280"))
        if ctas:
            botoes_html = build_two_ctas(ctas)
        else:
            botoes_html = '<p style="margin-top:20px;"><span style="color: #6b7280;">Set APP_BASE_URL to display links.</span></p>'

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

        current_app.logger.info(
            "Notificação por e-mail: enviando gatilho para Power Automate em %s (responsável: %s)",
            relay_email,
            responsavel_usuario.email,
        )
        ok, err = enviar_email(relay_email, assunto, corpo_html, corpo_texto)
        if ok:
            current_app.logger.info("E-mail gatilho enviado com sucesso para %s", relay_email)
        else:
            current_app.logger.warning(
                "Falha ao enviar e-mail gatilho para %s: %s",
                relay_email,
                err or "verifique MAIL_* e logs",
            )
    else:
        logger.debug("Aprovador sem e-mail cadastrado; notificação por e-mail não enviada")


# ---------- Notificação para supervisores de setores adicionados ao chamado ----------


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
    """Dispara evento para Power Automate avisando prazo de 24h ao responsável."""
    if not responsavel_email or not str(responsavel_email).strip():
        logger.warning(
            "Alerta de prazo 24h ignorado para chamado %s: responsável sem e-mail",
            numero_chamado,
        )
        return
    responsavel_email = responsavel_email.strip()
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    resumo_truncado = (descricao_resumo or "")[:500] + (
        "..." if len(descricao_resumo or "") > 500 else ""
    )
    corpo_texto = (
        f"Number: {numero_chamado}\n"
        "Deadline warning: this ticket is approaching SLA due time (24h remaining).\n"
        f"Category: {categoria}\n"
        f"Type: {tipo_solicitacao}\n"
        f"Area: {area}\n"
        f"Requester: {solicitante_nome}\n"
        f"Summary: {resumo_truncado}\n\n"
        "Use the buttons in the email to access: View ticket history or View your sector tickets."
    )
    detalhes_html = build_detail_table(
        [
            ("Number", numero_chamado),
            ("Category", categoria),
            ("Type", tipo_solicitacao),
            ("Area", area),
            ("Requester", solicitante_nome),
        ]
    )
    summary_html = f'<p style="margin: 12px 0;">{escape(resumo_truncado)}</p>'

    ctas = []
    if link:
        ctas.append(("View ticket history", link, "#d97706"))
    if link_dash:
        ctas.append(("View your sector tickets", link_dash, "#6b7280"))
    if ctas:
        botoes_html = build_two_ctas(ctas)
    else:
        botoes_html = '<p style="margin-top:20px;"><span style="color: #6b7280;">Set APP_BASE_URL to display links.</span></p>'

    corpo_html = build_email_shell(
        header_title="Ticket nearing deadline (24h)",
        header_color="#d97706",
        body_html=(
            "<p>Hello, this ticket is approaching its deadline.</p>"
            + detalhes_html
            + summary_html
            + botoes_html
        ),
    )
    _disparar_evento_power_automate(
        PREFIXO_ASSUNTO_CHAMADO_PRAZO_24H,
        numero_chamado,
        responsavel_email,
        corpo_html,
        corpo_texto,
    )


def notificar_novo_usuario_cadastrado(
    usuario_id: str,
    usuario_email: str,
    usuario_nome: str = "",
    perfil: str = "",
    areas: list | None = None,
    senha_inicial: str = "",
) -> None:
    """Dispara evento para Power Automate avisando o próprio usuário recém-cadastrado."""
    if not usuario_email or not str(usuario_email).strip():
        logger.warning("Aviso de novo usuário ignorado: e-mail do usuário vazio")
        return
    usuario_email = usuario_email.strip()
    destino_final = (_config("POWER_AUTOMATE_TEST_DEST_EMAIL") or "").strip() or usuario_email
    areas_str = ", ".join(areas or [])
    link_dash = _link_dashboard()
    corpo_texto = (
        f"Hello {usuario_nome or 'user'},\n"
        "A new account has been created with your email in DTX Digital Andon.\n"
        f"Profile: {perfil}\n"
        f"Areas: {areas_str or 'N/A'}\n"
        f"E-mail: {usuario_email}\n"
        f"Your initial password is: {senha_inicial}\n\n"
        "If you do not recognize this action, contact support immediately."
    )
    detalhes_html = build_detail_table(
        [
            ("Profile", perfil or "N/A"),
            ("Areas", areas_str or "N/A"),
            ("E-mail", usuario_email),
            ("Initial password", senha_inicial),
        ]
    )
    acesso_html = ""
    if link_dash:
        acesso_html = f'<p style="margin-top: 20px;">{build_cta_button("Open system", link_dash, "#2563eb")}</p>'

    corpo_html = build_email_shell(
        header_title="New user registration",
        header_color="#2563eb",
        body_html=(
            f"<p>Hello {escape(usuario_nome or 'user')}, a new account has been registered using your email.</p>"
            + detalhes_html
            + "<p>If you do not recognize this action, contact support immediately.</p>"
            + acesso_html
        ),
    )
    _disparar_evento_power_automate(
        PREFIXO_ASSUNTO_USUARIO_CADASTRADO,
        usuario_id,
        destino_final,
        corpo_html,
        corpo_texto,
    )


def notificar_responsavel_setor_adicional_power_automate(
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
    """
    Notifica o responsável de um setor adicional do chamado (via SMTP direto).

    Opção B: não usar assunto estruturado para Power Automate nesse tipo de notificação.
    """
    if not email_responsavel_setor or not str(email_responsavel_setor).strip():
        logger.warning(
            "Aviso setor adicional ignorado para chamado %s: e-mail do responsável vazio",
            numero_chamado,
        )
        return
    email_responsavel_setor = email_responsavel_setor.strip()
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    resumo_truncado = (descricao_resumo or "")[:500] + (
        "..." if len(descricao_resumo or "") > 500 else ""
    )
    corpo_texto = (
        f"Number: {numero_chamado}\n"
        f"Additional department included: {setor_adicional}\n"
        f"Included by: {quem_adicionou_nome}\n"
        f"Category: {categoria}\n"
        f"Type: {tipo_solicitacao}\n"
        f"Requester: {solicitante_nome}\n"
        f"Summary: {resumo_truncado}\n\n"
        "Use the buttons in the email to access: View ticket history or View your sector tickets."
    )
    detalhes_html = build_detail_table(
        [
            ("Number", numero_chamado),
            ("Department", setor_adicional),
            ("Included by", quem_adicionou_nome),
            ("Category", categoria),
            ("Type", tipo_solicitacao),
            ("Requester", solicitante_nome),
        ]
    )
    summary_html = f'<p style="margin: 12px 0;">{escape(resumo_truncado)}</p>'

    ctas = []
    if link:
        ctas.append(("View ticket history", link, "#2563eb"))
    if link_dash:
        ctas.append(("View your sector tickets", link_dash, "#6b7280"))
    if ctas:
        botoes_html = build_two_ctas(ctas)
    else:
        botoes_html = '<p style="margin-top:20px;"><span style="color: #6b7280;">Set APP_BASE_URL to display links.</span></p>'

    corpo_html = build_email_shell(
        header_title="Additional department included",
        header_color="#2563eb",
        body_html=(
            "<p>Hello, your department has been included in this ticket.</p>"
            + detalhes_html
            + summary_html
            + botoes_html
        ),
    )
    assunto = f"Ticket {numero_chamado}: your department has been included"
    ok, err = enviar_email(email_responsavel_setor, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info(
            "E-mail de setor adicional enviado para %s (chamado %s)",
            email_responsavel_setor,
            numero_chamado,
        )
    else:
        logger.warning(
            "Falha ao enviar e-mail de setor adicional para %s: %s",
            email_responsavel_setor,
            err or "verifique MAIL_*",
        )


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
    """
    Notifica todos os supervisores (e admins) dos setores adicionados ao chamado.
    Envia e-mail para cada usuário único (evita duplicata se estiver em mais de um setor).
    """
    if not setores_novos:
        return
    from app.models_usuario import Usuario

    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    setores_str = setores_nomes or ", ".join(setores_novos)

    from app.utils_areas import setor_para_area

    usuarios_unicos = {}  # id -> usuario
    for setor in setores_novos:
        areas_busca = [setor]
        area_norm = setor_para_area(setor)
        if area_norm and area_norm != setor:
            areas_busca.append(area_norm)
        for area in areas_busca:
            for u in Usuario.get_supervisores_por_area(area):
                if u and u.id and u.id not in usuarios_unicos:
                    usuarios_unicos[u.id] = u

    resumo_truncado = (descricao_resumo or "")[:500] + (
        "..." if len(descricao_resumo or "") > 500 else ""
    )

    for usuario in usuarios_unicos.values():
        email = getattr(usuario, "email", None)
        if not email or not str(email).strip():
            continue
        assunto = f"Ticket {numero_chamado}: your department has been included"
        corpo_texto = (
            f"Number: {numero_chamado}\n"
            f"Your department was included in this ticket by {quem_adicionou_nome}.\n"
            f"Departments added: {setores_str}\n"
            f"Category: {categoria}\nType: {tipo_solicitacao}\n"
            f"Requester: {solicitante_nome}\n"
            f"Summary: {resumo_truncado}\n\n"
            "Use the buttons in the email to access the ticket and view the list in your sector."
        )
        detalhes_html = build_detail_table(
            [
                ("Number", numero_chamado),
                ("Category", categoria),
                ("Type", tipo_solicitacao),
                ("Requester", solicitante_nome),
                ("Included by", quem_adicionou_nome),
                ("Departments added", setores_str),
            ]
        )
        summary_html = f'<p style="margin: 12px 0;">{escape(resumo_truncado)}</p>'

        ctas = []
        if link:
            ctas.append(("View ticket history", link, "#2563eb"))
        if link_dash:
            ctas.append(("View your sector tickets", link_dash, "#6b7280"))
        if ctas:
            botoes_html = build_two_ctas(ctas)
        else:
            botoes_html = '<p style="margin-top:20px;"><span style="color: #6b7280;">Set APP_BASE_URL to display links.</span></p>'

        corpo_html = build_email_shell(
            header_title="Ticket: your department has been included",
            header_color="#2563eb",
            body_html=(
                f"<p>Hello, ticket <strong>{escape(numero_chamado)}</strong> had your department included by <strong>{escape(quem_adicionou_nome)}</strong>.</p>"
                + detalhes_html
                + summary_html
                + botoes_html
            ),
        )
        ok, err = enviar_email(email.strip(), assunto, corpo_html, corpo_texto)
        if ok:
            logger.info(
                "E-mail setores adicionados enviado para %s (chamado %s)", email, numero_chamado
            )
        else:
            logger.warning(
                "Falha ao enviar e-mail setores adicionados para %s: %s",
                email,
                err or "verifique MAIL_*",
            )


# ---------- Notificação para SOLICITANTE - Decisão (Em Atendimento / Concluído) ----------


def notificar_solicitante_status(
    chamado_id: str, numero_chamado: str, novo_status: str, categoria: str, solicitante_usuario
) -> None:
    """Notifica o solicitante por e-mail sobre mudança de status (opt-in via NOTIFY_SOLICITANTE_EMAIL)."""
    if not _config("NOTIFY_SOLICITANTE_EMAIL"):
        return

    if not solicitante_usuario:
        return

    email = getattr(solicitante_usuario, "email", None) or ""
    if not email.strip():
        return

    nome = getattr(solicitante_usuario, "nome", None) or "Solicitante"
    link = _link_chamado(chamado_id)

    if novo_status == "Concluído":
        assunto = f"Chamado {escape(numero_chamado)} concluído"
        header_title = f"Chamado {escape(numero_chamado)}: Concluído"
        header_color = "#059669"
        msg_status = "seu chamado foi <strong>concluído</strong>"
    else:
        assunto = f"Chamado {escape(numero_chamado)} em atendimento"
        header_title = f"Chamado {escape(numero_chamado)}: Em Atendimento"
        header_color = "#2563eb"
        msg_status = "seu chamado está <strong>em atendimento</strong>"

    detalhes_html = build_detail_table(
        [("Chamado", numero_chamado), ("Categoria", categoria), ("Status", novo_status)]
    )
    botoes_html = (
        build_cta_button("Ver chamado", link, "#2563eb")
        if link
        else '<p style="color:#6b7280;">Acesse o sistema para acompanhar.</p>'
    )

    corpo_html = build_email_shell(
        header_title=header_title,
        header_color=header_color,
        body_html=(
            f"<p>Olá, <strong>{escape(nome)}</strong>! Informamos que {msg_status}.</p>"
            + detalhes_html
            + f'<p style="margin-top:20px;">{botoes_html}</p>'
        ),
    )

    corpo_texto = (
        f"Olá, {nome}!\n\n"
        f"Chamado: {numero_chamado}\nCategoria: {categoria}\nStatus: {novo_status}"
        + (f"\n\nVer chamado: {link}" if link else "")
    )

    ok, err = enviar_email(email.strip(), assunto, corpo_html, corpo_texto)
    if ok:
        logger.info(
            "E-mail de status (%s) enviado para %s (chamado %s)", novo_status, email, numero_chamado
        )
    else:
        logger.warning(
            "Falha ao enviar e-mail de status para %s: %s", email, err or "verifique MAIL_*"
        )
