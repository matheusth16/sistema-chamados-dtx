"""Serviço de MFA: TOTP (app autenticador) + códigos de backup de uso único."""

from __future__ import annotations

import base64
import io
import logging
import secrets

import pyotp
import segno
from werkzeug.security import check_password_hash, generate_password_hash

logger = logging.getLogger(__name__)

ISSUER_NAME = "DTX Aerospace - Chamados"
BACKUP_CODES_COUNT = 10


def gerar_secret() -> str:
    """Gera um novo secret TOTP em base32."""
    return pyotp.random_base32()


def gerar_qr_code_data_uri(email: str, secret: str) -> str:
    """Gera QR code (PNG, data URI base64) da provisioning URI do TOTP."""
    uri = pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER_NAME)
    qr = segno.make(uri, error="m")
    buffer = io.BytesIO()
    qr.save(buffer, kind="png", scale=6, border=2)
    b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def verificar_codigo_totp(secret: str, codigo: str) -> bool:
    """Valida um código de 6 dígitos contra o secret TOTP (janela de tolerância de 1)."""
    if not secret or not codigo:
        return False
    codigo_normalizado = codigo.strip().replace(" ", "")
    try:
        return pyotp.TOTP(secret).verify(codigo_normalizado, valid_window=1)
    except Exception:
        logger.warning("Código TOTP malformado recebido na verificação")
        return False


def gerar_codigos_backup(quantidade: int = BACKUP_CODES_COUNT) -> list[str]:
    """Gera códigos de backup em texto plano (exibidos uma única vez ao usuário)."""
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(quantidade)]


def hash_codigos_backup(codigos: list[str]) -> list[str]:
    """Hasheia códigos de backup para armazenamento (nunca gravar texto plano)."""
    return [generate_password_hash(c) for c in codigos]


def verificar_e_consumir_codigo_backup(
    hashes: list[str] | None, codigo: str
) -> tuple[bool, list[str]]:
    """Valida um código de backup e o remove da lista (uso único).

    Retorna (True, lista_restante) se válido, (False, lista_original) caso contrário.
    """
    hashes = hashes or []
    codigo_normalizado = (codigo or "").strip().lower()
    if not codigo_normalizado:
        return False, hashes
    for h in hashes:
        if check_password_hash(h, codigo_normalizado):
            restantes = [x for x in hashes if x != h]
            return True, restantes
    return False, hashes
