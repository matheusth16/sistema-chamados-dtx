"""
Web Push: salvar inscrições (subscriptions) e enviar notificações ao navegador.
Requer VAPID_PUBLIC_KEY e VAPID_PRIVATE_KEY no .env (gerar com: python -m vapid --gen).
"""

import logging
import json
from typing import Any, Dict, List
from firebase_admin import firestore
from app.database import db

logger = logging.getLogger(__name__)


def salvar_inscricao(usuario_id: str, subscription: Dict[str, Any]) -> bool:
    """
    Salva a inscrição (PushSubscription) do navegador para o usuário.
    subscription deve ter: endpoint, keys { p256dh, auth }.
    """
    if not usuario_id or not subscription.get('endpoint'):
        return False
    try:
        keys = subscription.get('keys') or {}
        db.collection('push_subscriptions').add({
            'usuario_id': usuario_id,
            'endpoint': subscription['endpoint'],
            'p256dh': keys.get('p256dh'),
            'auth': keys.get('auth'),
            'created_at': firestore.SERVER_TIMESTAMP,
        })
        logger.debug(f"Web Push: inscrição salva para usuario={usuario_id}")
        return True
    except Exception as e:
        logger.exception(f"Erro ao salvar inscrição Web Push: {e}")
        return False


def obter_inscricoes(usuario_id: str) -> List[Dict[str, Any]]:
    """Retorna lista de subscription info para envio (endpoint + keys)."""
    if not usuario_id:
        return []
    try:
        docs = db.collection('push_subscriptions').where('usuario_id', '==', usuario_id).stream()
        out = []
        for doc in docs:
            d = doc.to_dict()
            out.append({
                'endpoint': d.get('endpoint'),
                'keys': {
                    'p256dh': d.get('p256dh'),
                    'auth': d.get('auth'),
                }
            })
        return [o for o in out if o.get('endpoint') and o.get('keys', {}).get('p256dh')]
    except Exception as e:
        logger.exception(f"Erro ao obter inscrições Web Push: {e}")
        return []


def enviar_webpush_usuario(usuario_id: str, titulo: str, corpo: str, url: str = None) -> int:
    """
    Envia notificação Web Push para todas as inscrições do usuário.
    Retorna quantidade de envios bem-sucedidos.
    """
    from flask import current_app
    try:
        vapid_private = getattr(current_app.config, 'VAPID_PRIVATE_KEY', None) or ''
        if not vapid_private:
            logger.debug("Web Push: VAPID_PRIVATE_KEY não configurada, ignorando.")
            return 0
        if isinstance(vapid_private, str) and '\\n' in vapid_private:
            vapid_private = vapid_private.replace('\\n', '\n')
    except RuntimeError:
        return 0
    try:
        import pywebpush
    except ImportError:
        logger.warning("pywebpush não instalado; Web Push desabilitado.")
        return 0

    subscriptions = obter_inscricoes(usuario_id)
    if not subscriptions:
        logger.debug(f"Web Push: nenhuma inscrição para usuario={usuario_id}")
        return 0

    payload = json.dumps({'title': titulo, 'body': corpo, 'url': url or ''})
    enviados = 0
    for sub in subscriptions:
        try:
            pywebpush.webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=vapid_private,
                vapid_claims={"sub": "mailto:noreply@sistema-chamados.local"}
            )
            enviados += 1
        except Exception as e:
            logger.warning(f"Web Push falhou para um dispositivo: {e}")
    return enviados
