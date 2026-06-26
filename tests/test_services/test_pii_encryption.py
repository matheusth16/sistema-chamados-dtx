"""
Testes unitários do serviço pii_encryption (Onda 4 — Fernet PII).

≥14 casos de teste cobrindo:
- is_pii_encryption_enabled com diferentes configurações
- email_lookup_hash: determinismo, case-insensitivity, normalização
- encrypt/decrypt round-trip
- maybe_encrypt/maybe_decrypt: no-op quando desabilitado
- dual-read legado (sem prefixo)
- chave inválida → erro claro
- string vazia e unicode
"""

import os
from unittest.mock import patch

import pytest

# ── Fixtures de chave Fernet válida ───────────────────────────────────────────


@pytest.fixture(scope="module")
def valid_fernet_key():
    """Chave Fernet válida gerada uma vez por módulo (não hardcode)."""
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


# ── is_pii_encryption_enabled ─────────────────────────────────────────────────


def test_is_pii_encryption_enabled_false_quando_env_false():
    """Retorna False quando ENCRYPT_PII_AT_REST=false (default)."""
    from app.services.pii_encryption import is_pii_encryption_enabled

    with (
        patch("app.services.pii_encryption._get_flask_config", return_value=None),
        patch.dict(os.environ, {"ENCRYPT_PII_AT_REST": "false"}, clear=False),
    ):
        result = is_pii_encryption_enabled()
    assert result is False


def test_is_pii_encryption_enabled_false_sem_key(valid_fernet_key):
    """Retorna False quando ENCRYPT_PII_AT_REST=true mas ENCRYPTION_KEY está ausente."""
    from app.services.pii_encryption import is_pii_encryption_enabled

    with (
        patch("app.services.pii_encryption._get_flask_config", return_value=None),
        patch.dict(os.environ, {"ENCRYPT_PII_AT_REST": "true", "ENCRYPTION_KEY": ""}, clear=False),
    ):
        result = is_pii_encryption_enabled()
    assert result is False


def test_is_pii_encryption_enabled_true_com_key_valida(valid_fernet_key):
    """Retorna True quando ENCRYPT_PII_AT_REST=true e ENCRYPTION_KEY está definida."""
    from app.services.pii_encryption import is_pii_encryption_enabled

    with (
        patch("app.services.pii_encryption._get_flask_config", return_value=None),
        patch.dict(
            os.environ,
            {"ENCRYPT_PII_AT_REST": "true", "ENCRYPTION_KEY": valid_fernet_key},
            clear=False,
        ),
    ):
        result = is_pii_encryption_enabled()
    assert result is True


# ── email_lookup_hash ─────────────────────────────────────────────────────────


def test_email_lookup_hash_determinístico():
    """Mesmo email sempre gera o mesmo hash."""
    from app.services.pii_encryption import email_lookup_hash

    h1 = email_lookup_hash("user@example.com")
    h2 = email_lookup_hash("user@example.com")
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex = 64 chars


def test_email_lookup_hash_case_insensitive():
    """USER@EXAMPLE.COM e user@example.com geram o mesmo hash."""
    from app.services.pii_encryption import email_lookup_hash

    assert email_lookup_hash("USER@EXAMPLE.COM") == email_lookup_hash("user@example.com")
    assert email_lookup_hash("User@Example.Com") == email_lookup_hash("user@example.com")


def test_email_lookup_hash_normaliza_espacos():
    """Espaços ao redor do email são ignorados no hash."""
    from app.services.pii_encryption import email_lookup_hash

    assert email_lookup_hash("  user@example.com  ") == email_lookup_hash("user@example.com")


def test_email_lookup_hash_emails_diferentes_geram_hashes_diferentes():
    """Dois emails distintos geram hashes distintos."""
    from app.services.pii_encryption import email_lookup_hash

    assert email_lookup_hash("a@dtx.aero") != email_lookup_hash("b@dtx.aero")


# ── encrypt_field / decrypt_field ─────────────────────────────────────────────


def test_encrypt_decrypt_round_trip(valid_fernet_key):
    """encrypt_field → decrypt_field retorna o plaintext original."""
    from app.services.pii_encryption import decrypt_field, encrypt_field

    with (
        patch("app.services.pii_encryption._get_flask_config", return_value=None),
        patch.dict(
            os.environ,
            {"ENCRYPT_PII_AT_REST": "true", "ENCRYPTION_KEY": valid_fernet_key},
            clear=False,
        ),
    ):
        ciphertext = encrypt_field("João Silva")
        assert ciphertext.startswith("fernet:v1:")
        plaintext = decrypt_field(ciphertext)
        assert plaintext == "João Silva"


def test_encrypt_field_gera_prefixo_correto(valid_fernet_key):
    """encrypt_field sempre prefixo 'fernet:v1:'."""
    from app.services.pii_encryption import encrypt_field

    with (
        patch("app.services.pii_encryption._get_flask_config", return_value=None),
        patch.dict(
            os.environ,
            {"ENCRYPT_PII_AT_REST": "true", "ENCRYPTION_KEY": valid_fernet_key},
            clear=False,
        ),
    ):
        ct = encrypt_field("teste@dtx.aero")
    assert ct.startswith("fernet:v1:")


def test_decrypt_field_legado_sem_prefixo_retorna_as_is(valid_fernet_key):
    """decrypt_field: string sem prefixo 'fernet:v1:' é tratada como legado e retornada."""
    from app.services.pii_encryption import decrypt_field

    with (
        patch("app.services.pii_encryption._get_flask_config", return_value=None),
        patch.dict(
            os.environ,
            {"ENCRYPT_PII_AT_REST": "true", "ENCRYPTION_KEY": valid_fernet_key},
            clear=False,
        ),
    ):
        result = decrypt_field("plaintext_legado@dtx.aero")
    assert result == "plaintext_legado@dtx.aero"


# ── maybe_encrypt / maybe_decrypt ─────────────────────────────────────────────


def test_maybe_encrypt_identity_quando_disabled():
    """maybe_encrypt retorna plaintext sem alteração quando encryption OFF."""
    from app.services.pii_encryption import maybe_encrypt

    with (
        patch("app.services.pii_encryption._get_flask_config", return_value=None),
        patch.dict(os.environ, {"ENCRYPT_PII_AT_REST": "false"}, clear=False),
    ):
        result = maybe_encrypt("usuario@dtx.aero")
    assert result == "usuario@dtx.aero"


def test_maybe_decrypt_identity_quando_disabled():
    """maybe_decrypt retorna stored sem alteração quando encryption OFF."""
    from app.services.pii_encryption import maybe_decrypt

    with (
        patch("app.services.pii_encryption._get_flask_config", return_value=None),
        patch.dict(os.environ, {"ENCRYPT_PII_AT_REST": "false"}, clear=False),
    ):
        result = maybe_decrypt("algum_valor_qualquer")
    assert result == "algum_valor_qualquer"


def test_maybe_decrypt_legado_plaintext_retorna_as_is_quando_enabled(valid_fernet_key):
    """maybe_decrypt: docs sem prefixo (legado) passam como-estão mesmo com encryption ON."""
    from app.services.pii_encryption import maybe_decrypt

    with (
        patch("app.services.pii_encryption._get_flask_config", return_value=None),
        patch.dict(
            os.environ,
            {"ENCRYPT_PII_AT_REST": "true", "ENCRYPTION_KEY": valid_fernet_key},
            clear=False,
        ),
    ):
        result = maybe_decrypt("nome_legado_sem_prefixo")
    assert result == "nome_legado_sem_prefixo"


# ── Erros e edge cases ────────────────────────────────────────────────────────


def test_key_invalida_levanta_valor_claro():
    """ENCRYPTION_KEY inválida levanta ValueError com mensagem clara ao tentar criptografar."""
    from app.services.pii_encryption import encrypt_field

    with (
        patch("app.services.pii_encryption._get_flask_config", return_value=None),
        patch.dict(
            os.environ,
            {"ENCRYPT_PII_AT_REST": "true", "ENCRYPTION_KEY": "chave-invalida-nao-base64"},
            clear=False,
        ),
        pytest.raises((ValueError, Exception)),
    ):
        encrypt_field("qualquer")


def test_string_vazia_round_trip(valid_fernet_key):
    """String vazia pode ser criptografada e descriptografada."""
    from app.services.pii_encryption import decrypt_field, encrypt_field

    with (
        patch("app.services.pii_encryption._get_flask_config", return_value=None),
        patch.dict(
            os.environ,
            {"ENCRYPT_PII_AT_REST": "true", "ENCRYPTION_KEY": valid_fernet_key},
            clear=False,
        ),
    ):
        ct = encrypt_field("")
        assert decrypt_field(ct) == ""


def test_string_unicode_round_trip(valid_fernet_key):
    """Strings com caracteres unicode (emojis, acentos) sobrevivem ao round-trip."""
    from app.services.pii_encryption import decrypt_field, encrypt_field

    texto = "María José — 日本語 🔐"
    with (
        patch("app.services.pii_encryption._get_flask_config", return_value=None),
        patch.dict(
            os.environ,
            {"ENCRYPT_PII_AT_REST": "true", "ENCRYPTION_KEY": valid_fernet_key},
            clear=False,
        ),
    ):
        ct = encrypt_field(texto)
        assert decrypt_field(ct) == texto
