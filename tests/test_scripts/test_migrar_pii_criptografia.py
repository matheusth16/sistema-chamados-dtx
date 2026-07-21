"""
TDD — Polish Onda 4: _decide_migration_update e migrar() com edge cases.

Cobre 3 estados de migração + casos limite:
1. Doc completo (prefix + hash) → None (skip)
2. Plaintext + sem hash → encrypt + hash (migração completa)
3. Prefix + sem hash → apenas hash (fix do bug de double-encrypt)
4. Email vazio → None (skip)
5. migrar() skips doc já migrado
6. migrar() apply: commita doc elegível
7. migrar() dry-run: não chama _commit_batch
"""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pytest

_FERNET_PREFIX = "fernet:v1:"


@pytest.fixture(scope="module")
def fernet():
    from cryptography.fernet import Fernet

    return Fernet(Fernet.generate_key())


def _make_doc(doc_id: str, data: dict) -> MagicMock:
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = data
    return doc


# ── _decide_migration_update — pure function ──────────────────────────────────


def test_decide_doc_completo_retorna_none(fernet):
    """Doc com prefix + hash já migrado → None (skip)."""
    from scripts.migrations.migrar_pii_criptografia import _decide_migration_update

    email_enc = _FERNET_PREFIX + fernet.encrypt(b"user@dtx.aero").decode()
    nome_enc = _FERNET_PREFIX + fernet.encrypt(b"User").decode()
    data = {"email": email_enc, "nome": nome_enc, "email_lookup_hash": "abc123hash"}
    assert _decide_migration_update(data, fernet) is None


def test_decide_plaintext_sem_hash_encripta_e_hash(fernet):
    """Plaintext + sem hash → dict com email/nome criptografado + hash correto."""
    from scripts.migrations.migrar_pii_criptografia import _decide_migration_update

    data = {"email": "user@dtx.aero", "nome": "Fulano"}
    result = _decide_migration_update(data, fernet)

    assert result is not None
    assert result["email"].startswith(_FERNET_PREFIX)
    assert result["nome"].startswith(_FERNET_PREFIX)
    assert "email_lookup_hash" in result
    expected_hash = hashlib.sha256(b"user@dtx.aero").hexdigest()
    assert result["email_lookup_hash"] == expected_hash


def test_decide_prefix_sem_hash_apenas_adiciona_hash_sem_reencriptar(fernet):
    """Prefix + sem hash: apenas adiciona email_lookup_hash — não re-criptografa email."""
    from scripts.migrations.migrar_pii_criptografia import _decide_migration_update

    plain = b"partial@dtx.aero"
    email_enc = _FERNET_PREFIX + fernet.encrypt(plain).decode()
    data = {"email": email_enc, "nome": "Nome", "email_lookup_hash": ""}

    result = _decide_migration_update(data, fernet)

    assert result is not None
    # email NÃO deve estar no update (já criptografado — fix do double-encrypt)
    assert "email" not in result, "email não deve ser re-criptografado"
    assert "nome" not in result, "nome não deve ser re-criptografado"
    # Apenas hash adicionado
    assert "email_lookup_hash" in result
    expected_hash = hashlib.sha256(plain.decode().strip().lower().encode()).hexdigest()
    assert result["email_lookup_hash"] == expected_hash


def test_decide_email_vazio_retorna_none(fernet):
    """Email vazio → None (skip sem atualizar)."""
    from scripts.migrations.migrar_pii_criptografia import _decide_migration_update

    assert _decide_migration_update({"email": "", "nome": "X"}, fernet) is None
    assert _decide_migration_update({"nome": "X"}, fernet) is None


# ── migrar() com mocks ────────────────────────────────────────────────────────


def test_migrar_doc_completo_skip(fernet):
    """migrar(): doc já migrado → pulados=1, atualizados=0, _commit_batch não chamado."""
    email_enc = _FERNET_PREFIX + fernet.encrypt(b"done@dtx.aero").decode()
    doc = _make_doc(
        "uid1",
        {
            "email": email_enc,
            "nome": _FERNET_PREFIX + fernet.encrypt(b"Done").decode(),
            "email_lookup_hash": "somehash",
        },
    )
    db = MagicMock()

    from scripts.migrations.migrar_pii_criptografia import migrar

    with (
        patch(
            "scripts.migrations.migrar_pii_criptografia._iter_collection_paginated",
            return_value=iter([doc]),
        ),
        patch("scripts.migrations.migrar_pii_criptografia._commit_batch") as mock_commit,
    ):
        stats = migrar(db, fernet, dry_run=False)

    assert stats["atualizados"] == 0
    assert stats["pulados"] == 1
    mock_commit.assert_not_called()


def test_migrar_plaintext_apply_encripta_e_commita(fernet):
    """migrar() apply: doc plaintext → atualizados=1, _commit_batch chamado uma vez."""
    doc = _make_doc("uid2", {"email": "novo@dtx.aero", "nome": "Novo"})
    db = MagicMock()

    from scripts.migrations.migrar_pii_criptografia import migrar

    with (
        patch(
            "scripts.migrations.migrar_pii_criptografia._iter_collection_paginated",
            return_value=iter([doc]),
        ),
        patch("scripts.migrations.migrar_pii_criptografia._commit_batch") as mock_commit,
    ):
        stats = migrar(db, fernet, dry_run=False)

    assert stats["atualizados"] == 1
    assert stats["erros"] == 0
    mock_commit.assert_called_once()


def test_migrar_dry_run_nao_chama_commit_batch(fernet):
    """migrar(dry_run=True): docs elegíveis contados mas _commit_batch NÃO chamado."""
    doc = _make_doc("uid3", {"email": "dry@dtx.aero", "nome": "Dry"})
    db = MagicMock()

    from scripts.migrations.migrar_pii_criptografia import migrar

    with (
        patch(
            "scripts.migrations.migrar_pii_criptografia._iter_collection_paginated",
            return_value=iter([doc]),
        ),
        patch("scripts.migrations.migrar_pii_criptografia._commit_batch") as mock_commit,
    ):
        stats = migrar(db, fernet, dry_run=True)

    assert stats["atualizados"] == 1
    mock_commit.assert_not_called()
