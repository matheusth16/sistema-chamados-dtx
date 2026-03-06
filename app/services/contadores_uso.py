"""
Contadores de uso por usuário por dia (relatórios e export).

Usado para limite opcional por usuário: cada um pode gerar no máximo N
"ações pesadas" por dia (atualizar relatório, exportar Excel), evitando
limite global injusto quando todos compartilham o mesmo sistema.
"""
import logging
from datetime import datetime
from typing import Optional, Tuple

from app.database import db

try:
    from google.cloud.firestore_v1 import Increment
except ImportError:
    Increment = None

logger = logging.getLogger(__name__)

COLLECTION = "contadores_uso"
CAMPO_RELATORIO = "relatorio_geracoes"
CAMPO_EXPORT = "export_excel_geracoes"


def _doc_id(user_id: str) -> str:
    """ID do documento: user_id + data YYYY-MM-DD."""
    hoje = datetime.utcnow().strftime("%Y-%m-%d")
    return f"{user_id}_{hoje}"


def verificar_e_incrementar_relatorio(
    user_id: str, limite_diario: int
) -> Tuple[bool, Optional[str]]:
    """
    Verifica se o usuário pode gerar mais uma "atualização de relatório" hoje.
    Se sim, incrementa o contador e retorna (True, None).
    Se não, retorna (False, mensagem_erro).
    Se limite_diario <= 0, não aplica limite (retorna True).
    """
    if not user_id or limite_diario <= 0:
        return (True, None)
    doc_id = _doc_id(user_id)
    try:
        doc_ref = db.collection(COLLECTION).document(doc_id)
        doc = doc_ref.get()
        atual = 0
        if doc.exists:
            atual = doc.to_dict().get(CAMPO_RELATORIO, 0) or 0
        if atual >= limite_diario:
            return (
                False,
                f"Você atingiu o limite de {limite_diario} atualizações de relatório por dia. Tente amanhã.",
            )
        if doc.exists:
            doc_ref.update({CAMPO_RELATORIO: Increment(1)})
        else:
            doc_ref.set(
                {
                    "user_id": user_id,
                    "data": datetime.utcnow().strftime("%Y-%m-%d"),
                    CAMPO_RELATORIO: 1,
                },
                merge=True,
            )
        return (True, None)
    except Exception as e:
        logger.warning("Contador de uso (relatório): %s", e)
        return (True, None)


def verificar_e_incrementar_export(
    user_id: str, limite_diario: int
) -> Tuple[bool, Optional[str]]:
    """
    Verifica se o usuário pode gerar mais um export Excel hoje.
    Se sim, incrementa e retorna (True, None). Senão (False, mensagem).
    Se limite_diario <= 0, não aplica limite.
    """
    if not user_id or limite_diario <= 0:
        return (True, None)
    doc_id = _doc_id(user_id)
    try:
        doc_ref = db.collection(COLLECTION).document(doc_id)
        doc = doc_ref.get()
        atual = 0
        if doc.exists:
            atual = doc.to_dict().get(CAMPO_EXPORT, 0) or 0
        if atual >= limite_diario:
            return (
                False,
                f"Você atingiu o limite de {limite_diario} exportações por dia. Tente amanhã.",
            )
        if doc.exists:
            doc_ref.update({CAMPO_EXPORT: Increment(1)})
        else:
            doc_ref.set(
                {
                    "user_id": user_id,
                    "data": datetime.utcnow().strftime("%Y-%m-%d"),
                    CAMPO_EXPORT: 1,
                },
                merge=True,
            )
        return (True, None)
    except Exception as e:
        logger.warning("Contador de uso (export): %s", e)
        return (True, None)
