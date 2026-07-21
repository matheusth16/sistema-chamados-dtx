"""
Migração Onda 4 — criptografia Fernet dos campos PII (`nome`, `email`) em usuários.

Converte documentos com nome/email em plaintext para:
  - `email`: fernet:v1:<token>
  - `nome`:  fernet:v1:<token>
  - `email_lookup_hash`: sha256(email.strip().lower()) em hex

Idempotente: pula docs que já têm email_lookup_hash e email com prefixo fernet:v1:.

Flags:
  --dry-run   (padrão) Lista o que seria feito, sem gravar nada.
  --apply     Executa as alterações no Firestore.

ORDEM OBRIGATÓRIA antes de --apply em produção:
  1. Criar índice Firestore em `email_lookup_hash` (single-field, ASC).
     Ver firestore.indexes.json, ADR-001 e docs/DEPLOYMENT_PLAN.md §Criptografia PII.
  2. Fazer backup dos dados (Firestore export).
  3. Rodar dry-run para confirmar contagem.
  4. Aplicar migração com --apply (app pode estar rodando; dual-read garante compatibilidade).
  5. Smoke test: tentar login com usuário migrado.
  6. Somente após 100% dos docs migrados: definir ENCRYPT_PII_AT_REST=true e reiniciar app.

Exige ENCRYPT_PII_AT_REST=true e ENCRYPTION_KEY válida no ambiente ao rodar --apply.

Uso:
  python scripts/migrations/migrar_pii_criptografia.py            # dry-run
  python scripts/migrations/migrar_pii_criptografia.py --apply    # executa
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from app.services.pii_encryption import email_lookup_hash as _pii_email_hash  # noqa: E402
from scripts.migrations._migration_utils import _commit_batch, _iter_collection_paginated  # noqa: E402

_FERNET_PREFIX = "fernet:v1:"


def _decide_migration_update(data: dict, fernet) -> dict | None:
    """Pure function — decide o que atualizar (ou None para pular).

    Trata 3 estados:
      (a) prefix + hash    → None (já migrado, skip)
      (b) prefix + sem hash → apenas adiciona email_lookup_hash (sem re-criptografar)
      (c) plaintext        → criptografa email + nome + adiciona hash

    Email vazio → None (skip).
    """
    email = data.get("email") or ""
    nome = data.get("nome") or ""
    has_hash = bool(data.get("email_lookup_hash"))
    has_prefix = isinstance(email, str) and email.startswith(_FERNET_PREFIX)

    if not email:
        return None

    # Já migrado completamente
    if has_prefix and has_hash:
        return None

    # Parcialmente migrado: criptografado mas sem hash — apenas adiciona hash
    if has_prefix:
        token = email[len(_FERNET_PREFIX) :]
        try:
            plaintext_email = fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except Exception as exc:
            raise ValueError(
                f"Não foi possível descriptografar email para gerar hash: {exc}"
            ) from exc
        return {"email_lookup_hash": _pii_email_hash(plaintext_email)}

    # Plaintext sem hash — migração completa
    email_enc = _FERNET_PREFIX + fernet.encrypt(email.encode("utf-8")).decode("ascii")
    nome_enc = (
        (_FERNET_PREFIX + fernet.encrypt(nome.encode("utf-8")).decode("ascii")) if nome else nome
    )
    return {
        "email": email_enc,
        "nome": nome_enc,
        "email_lookup_hash": _pii_email_hash(email),
    }


def _check_env() -> tuple[str, object]:
    """Valida ambiente e retorna (ENCRYPTION_KEY, Fernet instance). Falha se inválido."""
    encrypt_pii = os.getenv("ENCRYPT_PII_AT_REST", "false").lower() in ("true", "1", "yes")
    if not encrypt_pii:
        print(
            "\n[ERRO] ENCRYPT_PII_AT_REST não está definido como 'true'."
            "\nDefina ENCRYPT_PII_AT_REST=true e ENCRYPTION_KEY antes de rodar --apply."
        )
        sys.exit(1)

    key = os.getenv("ENCRYPTION_KEY", "").strip()
    if not key:
        print(
            "\n[ERRO] ENCRYPTION_KEY não está definida."
            "\nGere com: python scripts/gerar_chave_criptografia.py"
        )
        sys.exit(1)

    try:
        from cryptography.fernet import Fernet

        f = Fernet(key.encode("ascii"))
        return key, f
    except Exception as exc:
        print(f"\n[ERRO] ENCRYPTION_KEY inválida: {exc}")
        sys.exit(1)


def _init_firebase() -> None:
    import firebase_admin
    from firebase_admin import credentials

    try:
        firebase_admin.get_app()
    except ValueError:
        cred_path = os.path.join(ROOT, "credentials.json")
        if not os.path.exists(cred_path):
            raise FileNotFoundError(f"credentials.json não encontrado em: {cred_path}") from None
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)


def migrar(db, fernet, dry_run: bool) -> dict:
    prefix_label = "[DRY-RUN]" if dry_run else "[APPLY]"
    processados = 0
    atualizados = 0
    pulados = 0
    erros = 0
    pending: list = []

    print("\n=== usuarios — criptografia PII (nome + email) ===")

    for doc in _iter_collection_paginated(db.collection("usuarios")):
        processados += 1
        data = doc.to_dict()
        email_raw = data.get("email", "")

        try:
            update = _decide_migration_update(data, fernet)
        except Exception as exc:
            print(f"  [ERRO] doc={doc.id}: {exc}")
            erros += 1
            continue

        if update is None:
            if not email_raw:
                print(f"  [WARN] doc={doc.id} — campo email vazio, pulando")
            else:
                print(f"  [SKIP] doc={doc.id} — já migrado")
            pulados += 1
            continue

        keys_updating = list(update.keys())
        print(f"  {prefix_label} doc={doc.id} email={email_raw!r} -> atualizar {keys_updating}")

        if not dry_run:
            pending.append((doc.reference, update))
        atualizados += 1

    if not dry_run and pending:
        _commit_batch(db, pending)

    stats = {
        "processados": processados,
        "atualizados": atualizados,
        "pulados": pulados,
        "erros": erros,
    }
    print(
        f"\n  Processados: {processados} | Atualizados: {atualizados} "
        f"| Pulados: {pulados} | Erros: {erros}"
    )
    if erros > 0:
        print(f"\n  ⚠️  {erros} documento(s) com erro — revise antes de --apply em produção.")
    return stats


def main() -> None:
    dry_run = "--apply" not in sys.argv

    print("=" * 60)
    print(f"  migrar_pii_criptografia.py  |  modo: {'DRY-RUN' if dry_run else 'APPLY'}")
    print("=" * 60)

    if dry_run:
        print("\n  Use --apply para executar as alterações no Firestore.")
        print(
            "  Pré-requisitos OBRIGATÓRIOS antes de --apply em produção:\n"
            "    1. Criar índice Firestore em email_lookup_hash (single-field, ASC)\n"
            "       firestore.indexes.json já tem a entrada — deploy: firebase deploy --only firestore:indexes\n"
            "    2. Fazer backup dos dados (Firestore export)\n"
            "    3. Confirmar contagem com dry-run\n"
            "    4. Aplicar migração (app pode continuar rodando durante migração)\n"
            "    5. Somente após 100% migrado: ativar ENCRYPT_PII_AT_REST=true e reiniciar\n"
        )
        # Em dry-run não precisa de ENCRYPTION_KEY real — apenas lista
        _init_firebase()
        from firebase_admin import firestore as fs

        db = fs.client()

        class _FakeFernet:
            def encrypt(self, data):
                return b"<seria_criptografado>"

            def decrypt(self, token):
                return b"<plaintext_simulado>"

        migrar(db, _FakeFernet(), dry_run=True)
    else:
        _, fernet = _check_env()
        _init_firebase()
        from firebase_admin import firestore as fs

        db = fs.client()
        migrar(db, fernet, dry_run=False)

    print(
        "\n=== Concluído"
        + (" (nenhuma alteração gravada)" if dry_run else " (alterações gravadas)")
        + " ==="
    )

    if not dry_run:
        print(
            "\n  Próximo passo: smoke test de login com um usuário migrado."
            "\n  Se login falhar, verifique se ENCRYPTION_KEY usada no --apply"
            "\n  é a mesma configurada no servidor."
            "\n"
            "\n  Quando 100% dos docs migrados: ative ENCRYPT_PII_AT_REST=true e reinicie a app."
        )


if __name__ == "__main__":
    main()
