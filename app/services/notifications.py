"""
Serviço de Notificações: E-mail (Microsoft Graph ou SMTP) e Microsoft Teams (Incoming Webhook).

- Aprovador (responsável): notificado na criação do chamado (e-mail + Teams).
- Solicitante: notificado quando o status muda para Em Atendimento ou Concluído (e-mail + Teams).
"""

import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import quote as url_quote
import json

from dotenv import load_dotenv
from flask import current_app

logger = logging.getLogger(__name__)


def _config(key: str, default=None):
    """Lê valor da configuração Flask (ex.: MAIL_SERVER, TEAMS_WEBHOOK_URL). Retorna default se fora de app context."""
    return getattr(current_app.config, key, None) if current_app else default


def _ensure_env_loaded():
    """Carrega .env da raiz do projeto se ainda não estiver no ambiente (fallback quando Flask config não tem MAIL_*)."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    env_path = os.path.join(root, '.env')
    if os.path.isfile(env_path):
        load_dotenv(env_path, override=True)


def _mail_setting(key: str, default=None):
    """Lê MAIL_* do Flask config; se vazio, carrega .env e usa os.getenv."""
    try:
        val = getattr(current_app.config, key, None) if current_app else None
    except RuntimeError:
        val = None
    if val is not None and (key != 'MAIL_SERVER' or (isinstance(val, str) and val.strip())):
        return val
    _ensure_env_loaded()
    return os.getenv(key, default)


# --- Microsoft Graph (OAuth2 client credentials + sendMail) ---
GRAPH_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
GRAPH_SEND_MAIL_URL = "https://graph.microsoft.com/v1.0/users/{user_id}/sendMail"


def _graph_config(key: str, default=None):
    """Lê GRAPH_* do Flask config ou .env."""
    try:
        val = getattr(current_app.config, key, None) if current_app else None
    except RuntimeError:
        val = None
    if val is not None and (not isinstance(val, str) or (val and val.strip())):
        return (val.strip() if isinstance(val, str) else val) or None
    _ensure_env_loaded()
    v = os.getenv(key, default)
    return (v.strip() if isinstance(v, str) and v else v) or None


def _get_graph_token() -> str:
    """Obtém access token para Microsoft Graph (client credentials). Retorna '' se falhar."""
    tenant = _graph_config('GRAPH_TENANT_ID')
    client_id = _graph_config('GRAPH_CLIENT_ID')
    client_secret = _graph_config('GRAPH_CLIENT_SECRET')
    if not tenant or not client_id or not client_secret:
        return ''
    url = GRAPH_TOKEN_URL.format(tenant=tenant)
    body = (
        "grant_type=client_credentials"
        "&client_id=" + url_quote(client_id)
        + "&client_secret=" + url_quote(client_secret)
        + "&scope=" + url_quote("https://graph.microsoft.com/.default")
    ).encode("utf-8")
    try:
        req = Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return (data.get("access_token") or "").strip()
    except Exception as e:
        logger.exception("Falha ao obter token Graph: %s", e)
        return ""


def enviar_email_graph(destinatario: str, assunto: str, corpo_html: str, corpo_texto: str = None):
    """
    Envia e-mail via Microsoft Graph (sendMail).
    Retorna (True, None) se enviado com sucesso, (False, mensagem_erro) caso contrário.
    """
    destinatario = (destinatario or "").strip()
    if not destinatario:
        logger.warning("Notificação por e-mail ignorada: destinatário vazio")
        return (False, None)
    user_id = _graph_config("GRAPH_SEND_AS_USER")
    if not user_id:
        return (False, "GRAPH_SEND_AS_USER não configurado")
    token = _get_graph_token()
    if not token:
        return (False, "Falha ao obter token Graph")
    url = GRAPH_SEND_MAIL_URL.format(user_id=url_quote(user_id, safe=""))
    payload = {
        "message": {
            "subject": assunto,
            "body": {"contentType": "HTML", "content": corpo_html},
            "toRecipients": [{"emailAddress": {"address": destinatario}}],
        }
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + token)
        with urlopen(req, timeout=15) as resp:
            if resp.status in (200, 202):
                logger.info("E-mail (Graph) enviado para %s: %s", destinatario, assunto[:50])
                return (True, None)
            return (False, "Graph retornou %s" % resp.status)
    except HTTPError as e:
        body = (e.fp.read().decode("utf-8", errors="replace")[:500] if e.fp else str(e))
        logger.warning("Graph sendMail erro %s: %s", e.code, body)
        return (False, "Graph %s: %s" % (e.code, body))
    except Exception as e:
        logger.exception("Falha ao enviar e-mail (Graph) para %s: %s", destinatario, e)
        return (False, str(e))


def enviar_email(destinatario: str, assunto: str, corpo_html: str, corpo_texto: str = None):
    """
    Envia e-mail via SMTP (Outlook/Office 365 ou outro).
    Retorna (True, None) se enviado com sucesso, (False, mensagem_erro ou None) caso contrário.
    Se MAIL_SERVER não estiver configurado, não envia e retorna (False, None).
    Usa Flask config; se MAIL_SERVER estiver vazio, faz fallback para .env (os.getenv).
    """
    server = (_config('MAIL_SERVER') or os.getenv('MAIL_SERVER') or '').strip()
    if not server:
        _ensure_env_loaded()
        server = (os.getenv('MAIL_SERVER') or '').strip()
    if not server or not destinatario or not destinatario.strip():
        if not destinatario or not destinatario.strip():
            logger.warning("Notificação por e-mail ignorada: destinatário vazio")
        return (False, None)
    destinatario = destinatario.strip()

    port = _mail_setting('MAIL_PORT') or 587
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 587
    use_tls = _mail_setting('MAIL_USE_TLS')
    if use_tls is None:
        use_tls = True
    else:
        use_tls = str(use_tls).lower() in ('true', '1', 'yes')
    from_addr = (_mail_setting('MAIL_DEFAULT_SENDER') or _mail_setting('MAIL_USERNAME') or 'noreply@localhost').strip()
    user = (_mail_setting('MAIL_USERNAME') or '').strip()
    password = (_mail_setting('MAIL_PASSWORD') or '').strip()

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = assunto
        msg['From'] = from_addr
        msg['To'] = destinatario

        if corpo_texto:
            msg.attach(MIMEText(corpo_texto, 'plain', 'utf-8'))
        msg.attach(MIMEText(corpo_html, 'html', 'utf-8'))

        with smtplib.SMTP(server, port) as s:
            if use_tls:
                s.starttls()
            if user and password:
                s.login(user, password)
            s.sendmail(msg['From'], destinatario, msg.as_string())
        logger.info(f"E-mail enviado para {destinatario}: {assunto[:50]}")
        return (True, None)
    except Exception as e:
        logger.exception(f"Falha ao enviar e-mail para {destinatario}: {e}")
        return (False, str(e))


def enviar_teams(webhook_url: str, titulo: str, texto: str, link_url: str = None, link_texto: str = None) -> bool:
    """
    Envia mensagem para um canal do Microsoft Teams via Incoming Webhook.
    Retorna True se enviado com sucesso.
    """
    if not webhook_url or not webhook_url.strip():
        return False
    try:
        body = {"@type": "MessageCard", "@context": "https://schema.org/extensions", "summary": titulo}
        sections = [{"activityTitle": titulo, "activitySubtitle": texto, "markdown": True}]
        if link_url and link_texto:
            sections[0]["potentialAction"] = [{"@type": "OpenUri", "name": link_texto, "targets": [{"os": "default", "uri": link_url}]}]
        body["sections"] = sections
        data = json.dumps(body).encode('utf-8')
        req = Request(webhook_url, data=data, method='POST', headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=10) as resp:
            if resp.status in (200, 201):
                logger.info(f"Teams: mensagem enviada - {titulo[:50]}")
                return True
        return False
    except (URLError, HTTPError, OSError) as e:
        logger.warning(f"Falha ao enviar para Teams: {e}")
        return False


def _link_chamado(chamado_id: str) -> str:
    """URL para visualizar o chamado (histórico)."""
    base = (_config('APP_BASE_URL') or '').rstrip('/')
    return f"{base}/chamado/{chamado_id}/historico" if base else ''


def _link_dashboard() -> str:
    """URL do painel (admin/supervisor ou index)."""
    base = (_config('APP_BASE_URL') or '').rstrip('/')
    return f"{base}/admin" if base else ''


# ---------- Notificação para APROVADOR (responsável) - Novo chamado ----------

def notificar_aprovador_novo_chamado(chamado_id: str, numero_chamado: str, categoria: str,
                                     tipo_solicitacao: str, descricao_resumo: str, area: str,
                                     solicitante_nome: str, responsavel_usuario,
                                     solicitante_email: str = None) -> None:
    """
    Notifica o responsável (aprovador) que um novo chamado foi atribuído a ele.
    Envia e-mail via SMTP e posta no Teams se webhook configurado.
    """
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    titulo_teams = f"Novo chamado atribuído: {numero_chamado}"
    texto_teams = (
        f"**Categoria:** {categoria}  \n**Tipo:** {tipo_solicitacao}  \n**Área:** {area}  \n"
        f"**Solicitante:** {solicitante_nome}  \n**Resumo:** {descricao_resumo[:200]}{'...' if len(descricao_resumo) > 200 else ''}"
    )

    if responsavel_usuario and getattr(responsavel_usuario, 'email', None):
        # E-mail gatilho para Power Automate / Outlook (Delegated)
        relay_email = (
            _config('NOTIFY_RELAY_EMAIL')
            or os.getenv('NOTIFY_RELAY_EMAIL')
            or 'dtxls.support@dtx.aero'
        ).strip()
        assunto = f"CHAMADO_NOVO|{numero_chamado}|{responsavel_usuario.email}"
        resumo_truncado = descricao_resumo[:500] + ('...' if len(descricao_resumo) > 500 else '')
        solicitante_linha = solicitante_nome
        if solicitante_email and solicitante_email.strip():
            solicitante_linha += f" ({solicitante_email.strip()})"
        corpo_texto = (
            f"Número: {numero_chamado}\n"
            f"Categoria: {categoria}\n"
            f"Tipo: {tipo_solicitacao}\n"
            f"Área: {area}\n"
            f"Solicitante: {solicitante_linha}\n"
            f"Resumo: {resumo_truncado}\n\n"
            "Use os botões no e-mail (Ver chamado / Abrir painel) para acessar."
        )
        # Botões curtos no HTML; só exibe se houver link
        botoes_html = ""
        if link:
            botoes_html += f'<a href="{link}" style="background: #2563eb; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; margin-right: 8px; display: inline-block;">Ver chamado</a> '
        if link_dash:
            botoes_html += f'<a href="{link_dash}" style="background: #6b7280; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; display: inline-block;">Abrir painel (Gestão)</a>'
        if not botoes_html:
            botoes_html = '<span style="color: #6b7280;">Defina APP_BASE_URL para exibir os links.</span>'
        corpo_html = (
            f'<div style="font-family: Arial, sans-serif; max-width: 560px;">'
            f'<h2 style="color: #2563eb; margin-bottom: 16px;">Novo chamado atribuído</h2>'
            f'<p>Olá, um novo chamado foi atribuído a você.</p>'
            f'<ul style="background: #f3f4f6; padding: 16px 16px 16px 32px; border-radius: 8px; margin: 16px 0;">'
            f'<li><strong>Número:</strong> {numero_chamado}</li>'
            f'<li><strong>Categoria:</strong> {categoria}</li>'
            f'<li><strong>Tipo:</strong> {tipo_solicitacao}</li>'
            f'<li><strong>Área:</strong> {area}</li>'
            f'<li><strong>Solicitante:</strong> {solicitante_linha}</li>'
            f'</ul>'
            f'<p style="margin: 12px 0;">{resumo_truncado}</p>'
            f'<p style="margin-top: 20px;">{botoes_html}</p>'
            f'<p style="margin-top: 24px; color: #6b7280; font-size: 12px;"><em>Sistema de Chamados - DTX</em></p>'
            f'</div>'
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

    webhook = _config('TEAMS_WEBHOOK_URL')
    if webhook:
        enviar_teams(webhook, titulo_teams, texto_teams, link_url=link_dash, link_texto="Abrir painel")


# ---------- Notificação para SOLICITANTE - Decisão (Em Atendimento / Concluído) ----------

def notificar_solicitante_status(chamado_id: str, numero_chamado: str, novo_status: str,
                                 categoria: str, solicitante_usuario) -> None:
    """
    Notificação ao solicitante desativada: não envia e-mail nem Teams.
    Chamado mantido para possível reativação futura.
    """
    pass
