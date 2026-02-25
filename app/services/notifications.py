"""
Serviço de Notificações: E-mail (Resend API ou SMTP/Outlook) e Microsoft Teams (Incoming Webhook).

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
import json

from dotenv import load_dotenv
from flask import current_app

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


def _config(key: str, default=None):
    """Lê valor da configuração Flask (ex.: MAIL_SERVER, TEAMS_WEBHOOK_URL). Retorna default se fora de app context."""
    return getattr(current_app.config, key, None) if current_app else default


def _get_resend_api_key() -> str:
    """Retorna RESEND_API_KEY do Flask config ou do .env (com fallback de carregar .env da raiz do projeto)."""
    key = (_config('RESEND_API_KEY') or os.getenv('RESEND_API_KEY') or '').strip()
    if key:
        return key
    # Fallback: carrega .env da raiz do projeto (app/services/ -> app/ -> raiz)
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    env_path = os.path.join(root, '.env')
    if os.path.isfile(env_path):
        load_dotenv(env_path, override=True)
    return (os.getenv('RESEND_API_KEY') or '').strip()


def enviar_email(destinatario: str, assunto: str, corpo_html: str, corpo_texto: str = None) -> bool:
    """
    Envia e-mail via SMTP (Outlook/Office 365 ou outro).
    Retorna True se enviado com sucesso, False caso contrário.
    Se MAIL_SERVER não estiver configurado, não envia e retorna False.
    """
    server = _config('MAIL_SERVER') or ''
    if not server or not destinatario or not destinatario.strip():
        if not destinatario or not destinatario.strip():
            logger.warning("Notificação por e-mail ignorada: destinatário vazio")
        return False
    destinatario = destinatario.strip()
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = assunto
        msg['From'] = _config('MAIL_DEFAULT_SENDER') or _config('MAIL_USERNAME') or 'noreply@localhost'
        msg['To'] = destinatario

        if corpo_texto:
            msg.attach(MIMEText(corpo_texto, 'plain', 'utf-8'))
        msg.attach(MIMEText(corpo_html, 'html', 'utf-8'))

        with smtplib.SMTP(_config('MAIL_SERVER'), _config('MAIL_PORT') or 587) as s:
            if _config('MAIL_USE_TLS'):
                s.starttls()
            user = _config('MAIL_USERNAME')
            password = _config('MAIL_PASSWORD')
            if user and password:
                s.login(user, password)
            s.sendmail(msg['From'], destinatario, msg.as_string())
        logger.info(f"E-mail enviado para {destinatario}: {assunto[:50]}")
        return True
    except Exception as e:
        logger.exception(f"Falha ao enviar e-mail para {destinatario}: {e}")
        return False


def enviar_email_resend(destinatario: str, assunto: str, corpo_html: str, corpo_texto: str = None,
                        reply_to: str = None) -> bool:
    """
    Envia e-mail via API Resend.
    Retorna True se enviado com sucesso. Se RESEND_API_KEY não estiver configurado, retorna False.
    """
    api_key = _get_resend_api_key()
    if not api_key or not destinatario or not destinatario.strip():
        if not destinatario or not destinatario.strip():
            logger.warning("Notificação por e-mail ignorada: destinatário vazio")
        return False
    destinatario = destinatario.strip()
    from_email = _config('RESEND_FROM_EMAIL') or 'onboarding@resend.dev'
    from_name = _config('RESEND_FROM_NAME') or 'Sistema de Chamados'
    from_header = f"{from_name} <{from_email}>"
    payload = {
        "from": from_header,
        "to": [destinatario],
        "subject": assunto,
        "html": corpo_html,
    }
    if corpo_texto:
        payload["text"] = corpo_texto
    if reply_to and reply_to.strip():
        payload["reply_to"] = reply_to.strip()
    try:
        data = json.dumps(payload).encode('utf-8')
        req = Request(
            RESEND_API_URL,
            data=data,
            method='POST',
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}',
                'User-Agent': 'SistemaChamados/1.0',
            },
        )
        with urlopen(req, timeout=15) as resp:
            if resp.status in (200, 201):
                logger.info(f"E-mail (Resend) enviado para {destinatario}: {assunto[:50]}")
                return True
            body = resp.read().decode('utf-8', errors='replace') if resp else ''
            logger.warning(f"Resend retornou status {resp.status} para {destinatario}: {body[:500]}")
            return False
    except HTTPError as e:
        body = ''
        if e.fp:
            try:
                body = e.fp.read().decode('utf-8', errors='replace')[:500]
            except Exception:
                pass
        logger.warning(
            "Resend API erro %s para %s: %s",
            e.code, destinatario, body or str(e),
        )
        return False
    except (URLError, OSError) as e:
        logger.exception(f"Falha ao enviar e-mail (Resend) para {destinatario}: {e}")
        return False


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
    Envia e-mail via Resend (se RESEND_API_KEY configurado) ou SMTP; posta no Teams se webhook configurado.
    """
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    titulo_teams = f"Novo chamado atribuído: {numero_chamado}"
    texto_teams = (
        f"**Categoria:** {categoria}  \n**Tipo:** {tipo_solicitacao}  \n**Área:** {area}  \n"
        f"**Solicitante:** {solicitante_nome}  \n**Resumo:** {descricao_resumo[:200]}{'...' if len(descricao_resumo) > 200 else ''}"
    )

    if responsavel_usuario and getattr(responsavel_usuario, 'email', None):
        assunto = f"[Sistema de Chamados] Novo chamado atribuído: {numero_chamado}"
        linha_solicitante = f"<li><strong>Solicitante:</strong> {solicitante_nome}"
        if solicitante_email and solicitante_email.strip():
            linha_solicitante += f" ({solicitante_email})"
        linha_solicitante += "</li>"
        corpo_html = f"""
        <p>Olá, <strong>{responsavel_usuario.nome}</strong>.</p>
        <p>Um novo chamado foi atribuído a você.</p>
        <ul>
            <li><strong>Número:</strong> {numero_chamado}</li>
            <li><strong>Categoria:</strong> {categoria}</li>
            <li><strong>Tipo:</strong> {tipo_solicitacao}</li>
            <li><strong>Área:</strong> {area}</li>
            {linha_solicitante}
        </ul>
        <p>{descricao_resumo[:500]}{'...' if len(descricao_resumo) > 500 else ''}</p>
        <p><a href="{link}">Ver chamado</a> &nbsp;|&nbsp; <a href="{link_dash}">Abrir painel</a></p>
        <p><em>Sistema de Chamados</em></p>
        """
        corpo_texto = f"Novo chamado {numero_chamado} atribuído a você. Categoria: {categoria}, Solicitante: {solicitante_nome}. Ver: {link}"
        use_resend = bool(_get_resend_api_key())
        if use_resend:
            current_app.logger.info("Notificação por e-mail: usando Resend (API) para %s", responsavel_usuario.email)
        else:
            current_app.logger.info("Notificação por e-mail: usando SMTP (RESEND_API_KEY não definido ou vazio)")
        if use_resend:
            enviar_email_resend(
                responsavel_usuario.email,
                assunto,
                corpo_html,
                corpo_texto,
                reply_to=solicitante_email or None,
            )
        else:
            enviar_email(responsavel_usuario.email, assunto, corpo_html, corpo_texto)
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
