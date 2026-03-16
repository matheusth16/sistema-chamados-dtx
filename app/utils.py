"""
Funções utilitárias compartilhadas entre rotas.
"""
from datetime import datetime
from typing import Any

from firebase_admin import firestore
from flask import current_app, request

from app.database import db


def mask_email_for_log(email: str | None) -> str:
    """
    Em produção, mascara e-mail em logs (LGPD/segurança).
    Ex.: user@empresa.com -> u***@empresa.com
    """
    if not email or not isinstance(email, str) or "@" not in email:
        return email or ""
    try:
        if current_app.config.get("ENV") == "production":
            local, _, domain = email.strip().partition("@")
            if not local or not domain:
                return "***@***"
            return f"{local[0]}***@{domain}"
    except Exception:
        pass
    return email


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


def extrair_numero_chamado(numero_str: str | None) -> float:
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
            # transaction.get() aceita um DocumentReference, não uma lista
            result = transaction.get(contador_ref)
            # Em versões mais recentes da API, pode retornar um generator
            doc = next(result) if hasattr(result, '__next__') else result
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


def get_client_ip() -> str:
    """
    Obtém o endereço IP real do cliente, considerando proxies reversos.
    Verifica os headers X-Forwarded-For (lista de IPs), X-Real-IP e remote_addr.

    Returns:
        Endereço IP do cliente
    """
    # Verifica X-Forwarded-For (primeiro IP da lista é o cliente original)
    if request.headers.get('X-Forwarded-For'):
        # X-Forwarded-For pode conter múltiplos IPs (client, proxy1, proxy2...)
        # O primeiro é sempre o cliente original
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()

    # Verifica X-Real-IP (usado por alguns proxies reversos)
    if request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')

    # Fallback para request.remote_addr (conexão direta)
    return request.remote_addr or 'unknown'
