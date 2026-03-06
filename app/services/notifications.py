"""
Serviço de Notificações: E-mail (SMTP).

- Aprovador (responsável): notificado na criação do chamado (e-mail).
- Solicitante: notificado quando o status muda para Em Atendimento ou Concluído (e-mail; atualmente desativado).
"""

import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from flask import current_app, request

logger = logging.getLogger(__name__)


def _config(key: str, default=None):
    """Lê valor da configuração Flask (ex.: MAIL_SERVER). Retorna default se fora de app context."""
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


def _base_url() -> str:
    """URL base da aplicação (para links em e-mails). Usa config, .env ou request."""
    base = (_config('APP_BASE_URL') or '').strip()
    if not base:
        _ensure_env_loaded()
        base = (os.getenv('APP_BASE_URL') or '').strip()
    if not base:
        try:
            if request and getattr(request, 'url_root', None):
                base = request.url_root.rstrip('/')
        except RuntimeError:
            pass
    return base.rstrip('/') if base else ''


def _link_chamado(chamado_id: str) -> str:
    """URL para visualizar o chamado (histórico)."""
    base = _base_url()
    return f"{base}/chamado/{chamado_id}/historico" if base else ''


def _link_dashboard() -> str:
    """URL do painel (admin/supervisor ou index)."""
    base = _base_url()
    return f"{base}/admin" if base else ''


# ---------- Notificação para APROVADOR (responsável) - Novo chamado ----------

def notificar_aprovador_novo_chamado(chamado_id: str, numero_chamado: str, categoria: str,
                                     tipo_solicitacao: str, descricao_resumo: str, area: str,
                                     solicitante_nome: str, responsavel_usuario,
                                     solicitante_email: str = None) -> None:
    """
    Notifica o responsável (aprovador) que um novo chamado foi atribuído a ele.
    Envia e-mail via SMTP.
    """
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()

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


# ---------- Notificação para supervisores de setores adicionados ao chamado ----------

def notificar_setores_adicionais_chamado(chamado_id: str, numero_chamado: str, setores_novos: list,
                                         categoria: str, tipo_solicitacao: str, descricao_resumo: str,
                                         solicitante_nome: str, quem_adicionou_nome: str,
                                         setores_nomes: str = None) -> None:
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

    resumo_truncado = (descricao_resumo or '')[:500] + ('...' if len(descricao_resumo or '') > 500 else '')

    for usuario in usuarios_unicos.values():
        email = getattr(usuario, 'email', None)
        if not email or not str(email).strip():
            continue
        assunto = f"Chamado {numero_chamado}: seu setor foi incluído"
        corpo_texto = (
            f"Número: {numero_chamado}\n"
            f"Seu setor foi incluído neste chamado por {quem_adicionou_nome}.\n"
            f"Setores adicionados: {setores_str}\n"
            f"Categoria: {categoria}\nTipo: {tipo_solicitacao}\n"
            f"Solicitante: {solicitante_nome}\n"
            f"Resumo: {resumo_truncado}\n\n"
            "Use os botões no e-mail para acessar o chamado."
        )
        botoes_html = ""
        if link:
            botoes_html += f'<a href="{link}" style="background: #2563eb; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; margin-right: 8px; display: inline-block;">Ver chamado</a> '
        if link_dash:
            botoes_html += f'<a href="{link_dash}" style="background: #6b7280; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; display: inline-block;">Abrir painel</a>'
        if not botoes_html:
            botoes_html = '<span style="color: #6b7280;">Defina APP_BASE_URL para exibir os links.</span>'
        corpo_html = (
            f'<div style="font-family: Arial, sans-serif; max-width: 560px;">'
            f'<h2 style="color: #2563eb; margin-bottom: 16px;">Chamado: seu setor foi incluído</h2>'
            f'<p>Olá, o chamado <strong>{numero_chamado}</strong> teve seu setor incluído por <strong>{quem_adicionou_nome}</strong>.</p>'
            f'<p><strong>Setores adicionados:</strong> {setores_str}</p>'
            f'<ul style="background: #f3f4f6; padding: 16px 16px 16px 32px; border-radius: 8px; margin: 16px 0;">'
            f'<li><strong>Número:</strong> {numero_chamado}</li>'
            f'<li><strong>Categoria:</strong> {categoria}</li>'
            f'<li><strong>Tipo:</strong> {tipo_solicitacao}</li>'
            f'<li><strong>Solicitante:</strong> {solicitante_nome}</li>'
            f'</ul>'
            f'<p style="margin: 12px 0;">{resumo_truncado}</p>'
            f'<p style="margin-top: 20px;">{botoes_html}</p>'
            f'<p style="margin-top: 24px; color: #6b7280; font-size: 12px;"><em>Sistema de Chamados - DTX</em></p>'
            f'</div>'
        )
        ok, err = enviar_email(email.strip(), assunto, corpo_html, corpo_texto)
        if ok:
            logger.info("E-mail setores adicionados enviado para %s (chamado %s)", email, numero_chamado)
        else:
            logger.warning("Falha ao enviar e-mail setores adicionados para %s: %s", email, err or "verifique MAIL_*")


# ---------- Notificação para SOLICITANTE - Decisão (Em Atendimento / Concluído) ----------

def notificar_solicitante_status(chamado_id: str, numero_chamado: str, novo_status: str,
                                 categoria: str, solicitante_usuario) -> None:
    """
    Notificação ao solicitante desativada: não envia e-mail.
    Chamado mantido para possível reativação futura.
    """
    pass
