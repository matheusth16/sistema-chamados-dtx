"""
Serviço de criptografia para proteção de dados sensíveis em repouso (LGPD/segurança).

Utiliza Fernet (AES-128-CBC + HMAC-SHA256) para criptografia simétrica.
A chave deve ser definida em ENCRYPTION_KEY (32 bytes em base64; gere com: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())").

- Criptografia em repouso: campos PII podem ser criptografados antes de persistir no Firestore.
- Em trânsito: garantir HTTPS (SESSION_COOKIE_SECURE, HSTS) e TLS em conexões externas (SMTP, APIs).
"""

import base64
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_fernet_instance: Optional["Fernet"] = None


def _get_fernet():
    """Retorna instância Fernet se ENCRYPTION_KEY estiver configurada."""
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance
    try:
        from flask import current_app
        key_b64 = (current_app.config.get("ENCRYPTION_KEY") or "").strip()
    except Exception:
        key_b64 = ""
    if not key_b64:
        return None
    try:
        from cryptography.fernet import Fernet
        from cryptography.exceptions import InvalidKey
        key = key_b64.encode() if isinstance(key_b64, str) else key_b64
        _fernet_instance = Fernet(key)
        return _fernet_instance
    except InvalidKey as e:
        logger.warning("ENCRYPTION_KEY inválida (deve ser base64url 32 bytes): %s", e)
        return None
    except Exception as e:
        logger.warning("Criptografia não disponível: %s", e)
        return None


def encrypt_at_rest(plaintext: Optional[str]) -> Optional[str]:
    """
    Criptografa uma string para armazenamento em repouso.
    Retorna None se plaintext for None; retorna o valor em base64 se criptografia estiver ativa.
    Se ENCRYPTION_KEY não estiver definida ou for inválida, retorna o texto em claro (compatibilidade).
    """
    if plaintext is None or (isinstance(plaintext, str) and not plaintext.strip()):
        return plaintext
    plaintext = plaintext if isinstance(plaintext, bytes) else plaintext.encode("utf-8")
    f = _get_fernet()
    if f is None:
        return plaintext.decode("utf-8") if isinstance(plaintext, bytes) else plaintext
    try:
        return f.encrypt(plaintext).decode("ascii")
    except Exception as e:
        logger.warning("Falha ao criptografar: %s", e)
        return plaintext.decode("utf-8") if isinstance(plaintext, bytes) else str(plaintext)


def decrypt_at_rest(ciphertext: Optional[str]) -> Optional[str]:
    """
    Descriptografa uma string armazenada.
    Se o valor não for reconhecido como payload Fernet, retorna o valor original (compatibilidade com dados legados).
    """
    if ciphertext is None or (isinstance(ciphertext, str) and not ciphertext.strip()):
        return ciphertext
    f = _get_fernet()
    if f is None:
        return ciphertext
    try:
        if isinstance(ciphertext, str):
            ciphertext = ciphertext.encode("ascii")
        return f.decrypt(ciphertext).decode("utf-8")
    except Exception:
        # Dado legado em texto claro ou formato inválido
        return ciphertext.decode("utf-8") if isinstance(ciphertext, bytes) else ciphertext


def is_encryption_available() -> bool:
    """Retorna True se ENCRYPTION_KEY estiver configurada e válida."""
    return _get_fernet() is not None
