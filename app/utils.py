"""
Funções utilitárias compartilhadas entre rotas.
"""

import logging
from datetime import datetime
from typing import Any

from flask import current_app, request
from sqlalchemy import func, select

from app import db as db_module

logger = logging.getLogger(__name__)


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
    except Exception as e:
        logger.debug("Erro ao mascarar e-mail para log: %s", e)
    return email


def formatar_data_para_excel(val: Any) -> str:
    """Converte data (datetime, Firestore Timestamp ou str) para string no formato do Excel."""
    if val is None:
        return "-"
    if isinstance(val, str):
        return val
    if hasattr(val, "strftime"):
        return val.strftime("%d/%m/%Y %H:%M")
    if hasattr(val, "to_pydatetime"):
        return val.to_pydatetime().strftime("%d/%m/%Y %H:%M")
    if hasattr(val, "timestamp"):
        return datetime.fromtimestamp(val.timestamp()).strftime("%d/%m/%Y %H:%M")
    return "-"


def extrair_numero_chamado(numero_str: str | None) -> float:
    """Extrai número de 'CHM-XXXX' para ordenação numérica."""
    if not numero_str:
        return float("inf")
    try:
        return int(numero_str.replace("CHM-", ""))
    except (ValueError, AttributeError):
        return float("inf")


def gerar_numero_chamado() -> str:
    """
    Gera o próximo número de chamado sequencial no formato CHM-XXXX.
    Usa SEQUENCE nativa do Postgres (chamados_numero_seq) — atômica por
    construção do banco, sem precisar de transação explícita.
    """
    try:
        with db_module.SessionLocal() as session:
            novo_numero = session.execute(select(func.nextval("chamados_numero_seq"))).scalar()
        return f"CHM-{novo_numero:04d}"
    except Exception:
        current_app.logger.exception("Erro ao gerar número de chamado via sequence")
        timestamp_num = int(datetime.now().timestamp()) % 10000
        return f"CHM-{timestamp_num:04d}"


def get_client_ip() -> str:
    """Retorna o IP do cliente a partir de request.remote_addr.

    ProxyFix (configurado em create_app) já processou X-Forwarded-For
    e atualizou remote_addr com o IP correto quando há proxy reverso.
    Ler XFF diretamente permitiria que atacantes forjassem o IP e
    burlassem o lockout de brute-force.
    """
    return request.remote_addr or "unknown"
