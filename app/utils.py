"""
Funções utilitárias compartilhadas entre rotas.
"""
from datetime import datetime
from typing import Any, Optional
from app.database import db
from firebase_admin import firestore
from flask import current_app


def formatar_data_para_excel(val: Any) -> str:
    """Converte data (datetime, Firestore Timestamp ou str) para string no formato do Excel."""
    if val is None:
        return '-'
    if isinstance(val, str):
        return val
    if hasattr(val, 'strftime'):
        return val.strftime('%d/%m/%Y %H:%M')
    if hasattr(val, 'to_pydatetime'):
        return val.to_pydatetime().strftime('%d/%m/%Y %H:%M')
    if hasattr(val, 'timestamp'):
        return datetime.fromtimestamp(val.timestamp()).strftime('%d/%m/%Y %H:%M')
    return '-'


def extrair_numero_chamado(numero_str: Optional[str]) -> float:
    """Extrai número de 'CHM-XXXX' para ordenação numérica."""
    if not numero_str:
        return float('inf')
    try:
        return int(numero_str.replace('CHM-', ''))
    except (ValueError, AttributeError):
        return float('inf')


def gerar_numero_chamado() -> str:
    """
    Gera o próximo número de chamado sequencial no formato CHM-XXXX.
    Usa transação atômica com documento contador.
    """
    try:
        contador_ref = db.collection('_sistema').document('contador_chamados')

        @firestore.transactional
        def atualizar_contador(transaction):
            # Usar next() e iter() para obter o documento do generator
            doc = next(iter(transaction.get([contador_ref])))
            if doc.exists:
                proximo_numero = doc.get('proximo_numero') + 1
            else:
                proximo_numero = 1
            transaction.set(contador_ref, {'proximo_numero': proximo_numero})
            return proximo_numero

        transaction = db.transaction()
        novo_numero = atualizar_contador(transaction)
        return f'CHM-{novo_numero:04d}'
    except Exception:
        current_app.logger.exception('Erro ao gerar número de chamado via transação')
        timestamp_num = int(datetime.now().timestamp()) % 10000
        return f'CHM-{timestamp_num:04d}'
