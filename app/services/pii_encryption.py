"""Criptografia de PII em repouso (Fernet) — conformidade LGPD / CWI 2.3.

Ativação: ENCRYPT_PII_AT_REST=true + ENCRYPTION_KEY=<chave Fernet válida>
Default (ENCRYPT_PII_AT_REST=false): sem efeito; lê/grava plaintext como antes.

Formato armazenado nos campos `nome` e `email` quando ativado:
    fernet:v1:<token_base64url>

Docs Firestore sem prefixo são tratados como legado (plaintext) para compatibilidade
retroativa durante migração parcial.

Não logar ENCRYPTION_KEY nem plaintext de PII.
"""

from __future__ import annotations

import hashlib
import logging
import os

logger = logging.getLogger(__name__)

_FERNET_PREFIX = "fernet:v1:"


def _get_flask_config() -> dict | None:
    """Retorna current_app.config se dentro de contexto Flask, senão None."""
    try:
        from flask import current_app

        return current_app.config
    except RuntimeError:
        return None


def _encryption_key_configured() -> bool:
    """True se ENCRYPTION_KEY está definida (Flask config ou env)."""
    config = _get_flask_config()
    if config is not None:
        key = config.get("ENCRYPTION_KEY", "")
    else:
        key = os.getenv("ENCRYPTION_KEY", "")
    return bool(key)


def is_pii_encryption_enabled() -> bool:
    """True se ENCRYPT_PII_AT_REST=true e ENCRYPTION_KEY está definida."""
    config = _get_flask_config()
    if config is not None:
        enabled = config.get("ENCRYPT_PII_AT_REST", False)
    else:
        enabled = os.getenv("ENCRYPT_PII_AT_REST", "false").lower() in ("true", "1", "yes")
    return bool(enabled) and _encryption_key_configured()


def _get_fernet():
    """Retorna instância Fernet configurada. Levanta ValueError se key inválida."""
    config = _get_flask_config()
    if config is not None:
        key = config.get("ENCRYPTION_KEY", "")
    else:
        key = os.getenv("ENCRYPTION_KEY", "")

    if not key:
        raise ValueError("ENCRYPTION_KEY não configurada; não é possível criptografar PII")

    from cryptography.fernet import Fernet

    try:
        raw = key.encode("ascii") if isinstance(key, str) else key
        return Fernet(raw)
    except Exception as exc:
        raise ValueError(f"ENCRYPTION_KEY inválida: {exc}") from exc


def email_lookup_hash(email: str) -> str:
    """sha256 hex do email normalizado (strip + lowercase). Determinístico."""
    normalized = email.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def encrypt_field(plaintext: str) -> str:
    """Criptografa campo PII. Retorna 'fernet:v1:<token>'."""
    f = _get_fernet()
    token = f.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{_FERNET_PREFIX}{token}"


def decrypt_field(ciphertext: str) -> str:
    """Descriptografa campo PII.

    Se o valor não começa com 'fernet:v1:' (documento legado), retorna as-is
    para compatibilidade retroativa durante migração parcial.
    """
    if not ciphertext.startswith(_FERNET_PREFIX):
        return ciphertext
    token = ciphertext[len(_FERNET_PREFIX) :]
    f = _get_fernet()
    return f.decrypt(token.encode("ascii")).decode("utf-8")


def maybe_encrypt(plaintext: str) -> str:
    """Criptografa se encryption habilitada; senão retorna plaintext sem modificação."""
    if not is_pii_encryption_enabled():
        return plaintext
    return encrypt_field(plaintext)


def maybe_decrypt(stored: str) -> str:
    """Descriptografa valor Fernet quando possível; legado plaintext passa as-is.

    Descriptografa se encryption ON **ou** se o valor tem prefixo Fernet e
    ENCRYPTION_KEY está configurada (docs migrados com flag ainda false / app
    sem reinício após migração).
    """
    if not stored.startswith(_FERNET_PREFIX):
        return stored
    if is_pii_encryption_enabled() or _encryption_key_configured():
        try:
            return decrypt_field(stored)
        except Exception as exc:
            logger.warning("Falha ao descriptografar campo PII (valor omitido): %s", exc)
            return stored
    return stored
