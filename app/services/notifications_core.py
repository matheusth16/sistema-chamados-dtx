"""
Notification Core: infraestrutura de envio de e-mail via Microsoft Graph API.

Extraído de notifications.py — funções reutilizadas por todos os notificar_*
(resolução de importância, formatação de assunto, envio via Graph, links).

Required environment variables:
  GRAPH_TENANT_ID     — Azure AD Directory (tenant) ID
  GRAPH_CLIENT_ID     — Application (client) ID
  GRAPH_CLIENT_SECRET — Client secret value
  GRAPH_SENDER_EMAIL  — Sender mailbox (e.g. dtxls.support@dtx.aero)
"""

import logging
import os
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app, request

from app.i18n import (
    get_translated_category,
    get_translated_sector,
    get_translated_sector_list,
    get_translated_status,
)

_EMAIL_LANG = "en"
_VALID_IMPORTANCE: frozenset[str] = frozenset({"high", "normal", "low"})
_ALWAYS_HIGH_TIPOS: frozenset[str] = frozenset(
    {
        "prazo_24h",
        "transferencia_area",
        "escalonamento_colega",
        "chamado_reaberto",
        "escalada_resposta_gerencial",
        "escalada_resolucao_gerencial",
        "abertura_aog",
    }
)

logger = logging.getLogger(__name__)


def _tc(v: str) -> str:
    return get_translated_category(v, _EMAIL_LANG) if v else ""


def _ts(v: str) -> str:
    return get_translated_sector(v, _EMAIL_LANG) if v else ""


def _tsl(v: str) -> str:
    return get_translated_sector_list(v, _EMAIL_LANG) if v else ""


def _tst(v: str) -> str:
    return get_translated_status(v, _EMAIL_LANG) if v else ""


def _config(key: str, default=None):
    """Read value from Flask config. Returns default if outside app context."""
    try:
        return current_app.config.get(key, default)
    except RuntimeError:
        return default


def resolver_importance(
    tipo_notificacao: str,
    chamado_data: dict | None = None,
    *,
    destinatario_perfil: str | None = None,
    marco_sla: int | None = None,
    numero_lembrete: int | None = None,
) -> str:
    """Retorna 'high' | 'normal' | 'low' conforme tipo de notificação e contexto.

    Regras:
    - destinatario_perfil='solicitante' → sempre 'normal'
    - tipo relatorio → 'low'
    - tipos SLA/escalada/transferência/reabertura → 'high'
    - aviso_resolucao_supervisor: marco=80 → 'high', marco=50 → 'normal'
    - lembrete_confirmacao: lembrete>=2 → 'high', lembrete=1 → 'normal'
    - novo_chamado_aprovador: Projetos/AOG ou prioridade<=0 → 'high', demais → 'normal'
    """
    if destinatario_perfil == "solicitante":
        return "normal"

    if tipo_notificacao == "relatorio":
        return "low"

    if tipo_notificacao in _ALWAYS_HIGH_TIPOS:
        return "high"

    if tipo_notificacao == "aviso_resolucao_supervisor":
        return "high" if marco_sla == 80 else "normal"

    if tipo_notificacao == "lembrete_confirmacao":
        return "high" if (numero_lembrete is not None and numero_lembrete >= 2) else "normal"

    if tipo_notificacao == "novo_chamado_aprovador":
        data = chamado_data or {}
        prioridade = data.get("prioridade")
        if data.get("categoria") in ("Projetos", "AOG") or (
            prioridade is not None and prioridade <= 0
        ):
            return "high"

    return "normal"


def _prefixar_assunto_high(assunto: str, contexto: str) -> str:
    """Adiciona 'Action required: ' ao assunto para novo chamado Projetos/prioridade 0."""
    if contexto == "novo_chamado_projetos":
        return f"Action required: {assunto}"
    return assunto


def _enviar_via_graph(
    destinatario: str,
    assunto: str,
    corpo_html: str,
    corpo_texto: str | None,
    from_addr: str,
    importance: str = "normal",
) -> tuple:
    """Send e-mail via Microsoft Graph API (client credentials)."""
    import json

    tenant_id = os.getenv("GRAPH_TENANT_ID", "").strip()
    client_id = os.getenv("GRAPH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GRAPH_CLIENT_SECRET", "").strip()
    sender_email = os.getenv("GRAPH_SENDER_EMAIL", "").strip() or from_addr.strip()

    if not all([tenant_id, client_id, client_secret, sender_email]):
        return (
            False,
            "Incomplete configuration: set GRAPH_TENANT_ID, GRAPH_CLIENT_ID, "
            "GRAPH_CLIENT_SECRET and GRAPH_SENDER_EMAIL",
        )

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
        with urllib.request.urlopen(req_token, timeout=10) as resp:  # nosec B310
            token_resp = json.loads(resp.read().decode("utf-8"))
            access_token = token_resp.get("access_token")
            if not access_token:
                err = f"Token not obtained: {list(token_resp.keys())}"
                logger.warning(err)
                return (False, err)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        err = f"Graph token HTTP {e.code}: {body}"
        logger.warning("Failed to obtain Graph token: %s", err)
        return (False, err)
    except Exception as e:
        logger.exception("Failed to obtain Graph token for %s: %s", destinatario, e)
        return (False, f"OAuth2 token failure: {e}")

    payload = json.dumps(
        {
            "message": {
                "subject": assunto,
                "body": {"contentType": "HTML", "content": corpo_html},
                "toRecipients": [{"emailAddress": {"address": destinatario}}],
                "importance": importance,
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
                logger.info("E-mail sent via Graph to %s: %s", destinatario, assunto[:60])
                return (True, None)
            err = f"Graph sendMail unexpected status: {resp.status}"
            logger.warning(err)
            return (False, err)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        err = f"Graph sendMail HTTP {e.code}: {body}"
        logger.warning("Graph sendMail failed for %s: %s", destinatario, err)
        return (False, err)
    except Exception as e:
        logger.exception("Failed to send via Graph to %s: %s", destinatario, e)
        return (False, str(e))


def _email_envio_permitido() -> bool:
    """True quando o ambiente permite envio real (produção ou opt-in explícito)."""
    if _config("TESTING"):
        return False
    return bool(_config("NOTIFY_EMAIL_ENABLED", False))


def enviar_email(
    destinatario: str,
    assunto: str,
    corpo_html: str,
    corpo_texto: str = None,
    importance: str = "normal",
):
    """Send e-mail via Microsoft Graph API. Returns (True, None) or (False, error)."""
    if importance not in _VALID_IMPORTANCE:
        logger.warning("Invalid importance '%s'; falling back to 'normal'", importance)
        importance = "normal"
    if not destinatario or not destinatario.strip():
        logger.warning("Notification skipped: empty recipient")
        return (False, None)
    if not _email_envio_permitido():
        motivo = "TESTING" if _config("TESTING") else "NOTIFY_EMAIL_ENABLED=false"
        logger.info(
            "E-mail suppressed (%s): %s — %s",
            motivo,
            destinatario.strip(),
            assunto[:80],
        )
        return (True, None)
    from_addr = os.getenv("GRAPH_SENDER_EMAIL", "").strip() or "noreply@localhost"
    return _enviar_via_graph(
        destinatario.strip(), assunto, corpo_html, corpo_texto, from_addr, importance=importance
    )


def _base_url() -> str:
    base = (_config("APP_BASE_URL") or os.getenv("APP_BASE_URL") or "").strip()
    if not base:
        try:
            if request and getattr(request, "url_root", None):
                base = request.url_root.rstrip("/")
        except RuntimeError:
            pass
    return base.rstrip("/") if base else ""


def _link_chamado(chamado_id: str) -> str:
    base = _base_url()
    return f"{base}/chamado/{chamado_id}" if base else ""


def _link_historico(chamado_id: str) -> str:
    """Link para supervisores/admins — vai direto para o histórico do chamado."""
    base = _base_url()
    return f"{base}/chamado/{chamado_id}/historico" if base else ""


def _link_dashboard() -> str:
    base = _base_url()
    return f"{base}/admin" if base else ""
