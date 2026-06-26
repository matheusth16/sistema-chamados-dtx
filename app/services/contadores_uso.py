"""
Contadores de uso por usuário por dia (relatórios e export).

Usado para limite opcional por usuário: cada um pode gerar no máximo N
"ações pesadas" por dia (atualizar relatório, exportar Excel), evitando
limite global injusto quando todos compartilham o mesmo sistema.

A verificação e o incremento são feitos dentro de uma transação Firestore
(@firestore.transactional) para evitar race conditions (F-13): sem transação,
dois requests simultâneos podem ler o mesmo contador e ambos passarem no limite.
"""

import logging
from datetime import UTC, datetime, timedelta

from firebase_admin import firestore
from google.cloud.firestore_v1 import Increment

from app.database import db

logger = logging.getLogger(__name__)

COLLECTION = "contadores_uso"
CAMPO_RELATORIO = "relatorio_geracoes"
CAMPO_EXPORT = "export_excel_geracoes"


def _doc_id(user_id: str) -> str:
    """ID do documento: user_id + data YYYY-MM-DD."""
    hoje = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"{user_id}_{hoje}"


@firestore.transactional
def _verificar_incrementar_tx(transaction, doc_ref, campo, limite, user_id, data_str):
    """Verifica o limite e incrementa o contador atomicamente dentro de uma transação.

    Retorna True se a ação foi permitida, False se o limite foi atingido.
    """
    doc = doc_ref.get(transaction=transaction)
    atual = doc.to_dict().get(campo, 0) if doc.exists else 0
    if atual >= limite:
        return False
    if doc.exists:
        transaction.update(doc_ref, {campo: Increment(1)})
    else:
        transaction.set(
            doc_ref,
            {
                "user_id": user_id,
                "data": data_str,
                campo: 1,
            },
        )
    return True


def verificar_e_incrementar_relatorio(user_id: str, limite_diario: int) -> tuple[bool, str | None]:
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
        data_str = datetime.now(UTC).strftime("%Y-%m-%d")
        transaction = db.transaction()
        permitido = _verificar_incrementar_tx(
            transaction, doc_ref, CAMPO_RELATORIO, limite_diario, user_id, data_str
        )
        if not permitido:
            return (
                False,
                f"Você atingiu o limite de {limite_diario} atualizações de relatório por dia. Tente amanhã.",
            )
        return (True, None)
    except Exception as e:
        logger.warning("Contador de uso (relatório): %s", e)
        return (True, None)


_BATCH_SIZE = 500


def limpar_contadores_antigos(dias: int = 90, dry_run: bool = True) -> dict:
    """Remove documentos de contadores_uso com mais de `dias` dias.

    Política de retenção: 90 dias (ver docs/ARQUITETURA.md).
    Operação em batch Firestore (≤500 por commit) para respeitar limites da API.

    Args:
        dias: Documentos mais antigos que este número de dias serão removidos.
        dry_run: Se True, apenas conta e loga sem deletar (padrão seguro).

    Returns:
        {"removidos": int, "dry_run": bool, "erros": int}
    """
    corte = datetime.now(UTC) - timedelta(days=dias)
    corte_str = corte.strftime("%Y-%m-%d")

    removidos = 0
    erros = 0

    query = db.collection(COLLECTION).where("data", "<", corte_str)

    if dry_run:
        for _doc in query.stream():
            removidos += 1
        logger.info(
            "limpar_contadores_antigos (dry-run): dias=%d corte=%s encontrados=%d",
            dias,
            corte_str,
            removidos,
        )
        return {"removidos": removidos, "dry_run": True, "erros": erros}

    batch = None
    batch_count = 0

    for doc in query.stream():
        if batch is None:
            batch = db.batch()
        batch.delete(doc.reference)
        batch_count += 1
        if batch_count >= _BATCH_SIZE:
            batch.commit()
            removidos += batch_count
            batch = db.batch()
            batch_count = 0

    if batch is not None and batch_count > 0:
        batch.commit()
        removidos += batch_count

    logger.info(
        "limpar_contadores_antigos: dias=%d corte=%s removidos=%d erros=%d",
        dias,
        corte_str,
        removidos,
        erros,
    )
    return {"removidos": removidos, "dry_run": False, "erros": erros}


def verificar_e_incrementar_export(user_id: str, limite_diario: int) -> tuple[bool, str | None]:
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
        data_str = datetime.now(UTC).strftime("%Y-%m-%d")
        transaction = db.transaction()
        permitido = _verificar_incrementar_tx(
            transaction, doc_ref, CAMPO_EXPORT, limite_diario, user_id, data_str
        )
        if not permitido:
            return (
                False,
                f"Você atingiu o limite de {limite_diario} exportações por dia. Tente amanhã.",
            )
        return (True, None)
    except Exception as e:
        logger.warning("Contador de uso (export): %s", e)
        return (True, None)
