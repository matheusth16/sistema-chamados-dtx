"""Histórico persistente de ações administrativas sobre contas de usuário
(criação, edição, desativação, ativação, exclusão) — auditoria LGPD/CWI."""

import logging

from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.database import db

logger = logging.getLogger(__name__)

COLLECTION = "historico_usuarios"


def registrar_historico_usuario(
    usuario_alvo_id: str,
    usuario_alvo_nome: str,
    admin_id: str,
    admin_nome: str,
    acao: str,
    detalhe: str | None = None,
) -> bool:
    """Grava um registro de auditoria para ação administrativa sobre um usuário.

    acao: 'criacao', 'edicao', 'desativacao', 'ativacao', 'exclusao', 'anonimizacao'
    """
    payload = {
        "usuario_alvo_id": usuario_alvo_id,
        "usuario_alvo_nome": usuario_alvo_nome,
        "admin_id": admin_id,
        "admin_nome": admin_nome,
        "acao": acao,
        "data_acao": firestore.SERVER_TIMESTAMP,
    }
    if detalhe is not None:
        payload["detalhe"] = detalhe

    try:
        db.collection(COLLECTION).add(payload)
        return True
    except Exception:
        logger.exception(
            "Erro ao registrar histórico de usuário: usuario_alvo_id=%s acao=%s",
            usuario_alvo_id,
            acao,
        )
        return False


def obter_historico_usuario(usuario_alvo_id: str) -> list[dict]:
    """Retorna o histórico administrativo de um usuário, mais recente primeiro."""
    try:
        docs = (
            db.collection(COLLECTION)
            .where(filter=FieldFilter("usuario_alvo_id", "==", usuario_alvo_id))
            .order_by("data_acao", direction=firestore.Query.DESCENDING)
            .stream()
        )
        return [doc.to_dict() for doc in docs]
    except Exception:
        logger.exception("Erro ao buscar histórico do usuário: usuario_alvo_id=%s", usuario_alvo_id)
        return []
