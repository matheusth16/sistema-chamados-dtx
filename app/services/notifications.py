"""
Serviço de Notificações: E-mail (SMTP).

- Aprovador (responsável): notificado na criação do chamado (e-mail).
- Solicitante: notificado quando o status muda para Em Atendimento ou Concluído (e-mail; atualmente desativado).
"""

import logging
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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


def _mail_setting(key: str, default=None):
    """Lê MAIL_* do Flask config (que já carrega .env via config.py na inicialização).
    Fallback para os.getenv apenas se executado fora de app context."""
    val = _config(key)
    if val is not None and (not isinstance(val, str) or val.strip()):
        return val
    return os.getenv(key, default)


_SMTP_MAX_TENTATIVAS = 3
_SMTP_BACKOFF_BASE = 2.0  # segundos: 1s, 2s, 4s


def enviar_email(destinatario: str, assunto: str, corpo_html: str, corpo_texto: str = None):
    """
    Envia e-mail via SMTP com retry e backoff exponencial (até 3 tentativas).
    Retorna (True, None) se enviado com sucesso, (False, mensagem_erro ou None) caso contrário.
    Se MAIL_SERVER não estiver configurado, não envia e retorna (False, None).
    """
    server = _mail_setting("MAIL_SERVER", "").strip()
    if not server or not destinatario or not destinatario.strip():
        if not destinatario or not destinatario.strip():
            logger.warning("Notificação por e-mail ignorada: destinatário vazio")
        return (False, None)
    destinatario = destinatario.strip()

    port = _mail_setting("MAIL_PORT", 587)
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 587
    use_tls = _mail_setting("MAIL_USE_TLS")
    if use_tls is None:
        use_tls = True
    else:
        use_tls = str(use_tls).lower() in ("true", "1", "yes")
    from_addr = (
        _mail_setting("MAIL_DEFAULT_SENDER")
        or _mail_setting("MAIL_USERNAME")
        or "noreply@localhost"
    ).strip()
    user = (_mail_setting("MAIL_USERNAME") or "").strip()
    password = (_mail_setting("MAIL_PASSWORD") or "").strip()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = from_addr
    msg["To"] = destinatario
    if corpo_texto:
        msg.attach(MIMEText(corpo_texto, "plain", "utf-8"))
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))

    for tentativa in range(_SMTP_MAX_TENTATIVAS):
        try:
            with smtplib.SMTP(server, port) as s:
                if use_tls:
                    s.starttls()
                if user and password:
                    s.login(user, password)
                s.sendmail(msg["From"], destinatario, msg.as_string())
            logger.info("E-mail enviado para %s: %s", destinatario, assunto[:50])
            return (True, None)
        except Exception as e:
            if tentativa < _SMTP_MAX_TENTATIVAS - 1:
                espera = _SMTP_BACKOFF_BASE**tentativa
                logger.warning(
                    "Falha ao enviar e-mail para %s (tentativa %d/%d): %s. Retry em %.0fs.",
                    destinatario,
                    tentativa + 1,
                    _SMTP_MAX_TENTATIVAS,
                    e,
                    espera,
                )
                time.sleep(espera)
            else:
                logger.exception(
                    "Falha ao enviar e-mail para %s após %d tentativas: %s",
                    destinatario,
                    _SMTP_MAX_TENTATIVAS,
                    e,
                )
                return (False, str(e))
    return (False, "Nenhuma tentativa bem-sucedida")


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
    return _mail_setting("NOTIFY_RELAY_EMAIL", "dtxls.support@dtx.aero").strip()


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
        "A new account has been created with your email in Ticket System - DTX.\n"
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
    """
    Notificação ao solicitante desativada: não envia e-mail.
    Chamado mantido para possível reativação futura.
    """
    pass
