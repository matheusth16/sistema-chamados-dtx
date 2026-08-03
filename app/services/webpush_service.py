"""
Web Push: salvar inscrições (subscriptions) e enviar notificações ao navegador.
Requer VAPID_PUBLIC_KEY e VAPID_PRIVATE_KEY no .env (gerar com: python -m vapid --gen).

Fase 2: armazenamento migrado de Firestore para PostgreSQL.
"""

import json
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import db as db_module
from app.db.models.apoio import PushSubscriptionRow

logger = logging.getLogger(__name__)

MAX_INSCRICOES = 20


def salvar_inscricao(usuario_id: str, subscription: dict[str, Any]) -> bool:
    """
    Salva a inscrição (PushSubscription) do navegador para o usuário.
    subscription deve ter: endpoint, keys { p256dh, auth }.
    """
    if not usuario_id or not subscription.get("endpoint"):
        return False
    try:
        keys = subscription.get("keys") or {}
        endpoint = subscription["endpoint"]
        with db_module.SessionLocal() as session, session.begin():
            # Deduplicação: se usuario_id+endpoint já existe, atualiza em vez
            # de duplicar (mesma semântica do antigo .set(merge=True)).
            stmt = (
                pg_insert(PushSubscriptionRow)
                .values(
                    usuario_id=usuario_id,
                    endpoint=endpoint,
                    p256dh=keys.get("p256dh"),
                    auth=keys.get("auth"),
                )
                .on_conflict_do_update(
                    index_elements=["usuario_id", "endpoint"],
                    set_={
                        "p256dh": keys.get("p256dh"),
                        "auth": keys.get("auth"),
                        "updated_at": func.now(),
                    },
                )
            )
            session.execute(stmt)
        logger.debug("Web Push: inscrição salva/atualizada para usuario=%s", usuario_id)
        return True
    except Exception as e:
        logger.exception("Erro ao salvar inscrição Web Push: %s", e)
        return False


def obter_inscricoes(usuario_id: str) -> list[dict[str, Any]]:
    """Retorna lista de subscription info para envio (endpoint + keys)."""
    if not usuario_id:
        return []
    try:
        with db_module.SessionLocal() as session:
            rows = (
                session.execute(
                    select(PushSubscriptionRow)
                    .where(PushSubscriptionRow.usuario_id == usuario_id)
                    .limit(MAX_INSCRICOES)
                )
                .scalars()
                .all()
            )
        if len(rows) >= MAX_INSCRICOES:
            logger.warning(
                "Web Push: limite de inscrições atingido (%d) para usuario=%s",
                MAX_INSCRICOES,
                usuario_id,
            )
        out = [
            {
                "doc_id": row.id,
                "endpoint": row.endpoint,
                "keys": {"p256dh": row.p256dh, "auth": row.auth},
            }
            for row in rows
        ]
        return [o for o in out if o.get("endpoint") and o.get("keys", {}).get("p256dh")]
    except Exception as e:
        logger.exception("Erro ao obter inscrições Web Push: %s", e)
        return []


def _deletar_subscricao(doc_id) -> None:
    """Remove uma inscrição expirada/revogada."""
    if not doc_id:
        return
    try:
        with db_module.SessionLocal() as session, session.begin():
            row = session.get(PushSubscriptionRow, int(doc_id))
            if row is not None:
                session.delete(row)
        logger.debug("Web Push: inscrição expirada removida id=%s", doc_id)
    except Exception as exc:
        logger.warning("Erro ao remover subscription expirada: %s", exc)


def enviar_webpush_usuario(usuario_id: str, titulo: str, corpo: str, url: str = None) -> int:
    """
    Envia notificação Web Push para todas as inscrições do usuário.
    Retorna quantidade de envios bem-sucedidos.
    """
    from flask import current_app

    try:
        vapid_private = current_app.config.get("VAPID_PRIVATE_KEY") or ""
        if not vapid_private:
            logger.debug("Web Push: VAPID_PRIVATE_KEY não configurada, ignorando.")
            return 0
        if isinstance(vapid_private, str) and "\\n" in vapid_private:
            vapid_private = vapid_private.replace("\\n", "\n")
    except RuntimeError:
        return 0
    try:
        import pywebpush
    except ImportError:
        logger.warning("pywebpush não instalado; Web Push desabilitado.")
        return 0

    subscriptions = obter_inscricoes(usuario_id)
    if not subscriptions:
        logger.debug("Web Push: nenhuma inscrição para usuario=%s", usuario_id)
        return 0

    payload = json.dumps({"title": titulo, "body": corpo, "url": url or ""})
    enviados = 0
    for sub in subscriptions:
        # pywebpush exige subscription_info com apenas endpoint + keys.
        subscription_info = {"endpoint": sub["endpoint"], "keys": sub["keys"]}
        try:
            pywebpush.webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=vapid_private,
                vapid_claims={"sub": "mailto:noreply@dtx-andon.local"},
            )
            enviados += 1
        except pywebpush.WebPushException as e:
            response = getattr(e, "response", None)
            status_code = getattr(response, "status_code", None)
            if status_code in (404, 410):
                _deletar_subscricao(sub.get("doc_id"))
            logger.warning("Web Push falhou para um dispositivo: %s", e)
        except Exception as e:
            logger.warning("Web Push falhou para um dispositivo: %s", e)
    return enviados
