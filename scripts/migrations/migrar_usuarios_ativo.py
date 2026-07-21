"""
Migração Onda 2 — backfill do campo `ativo` em documentos de usuários.

Firestore docs criados antes da Onda 2 não têm o campo `ativo`.
Este script percorre a coleção `usuarios` e, para cada doc sem o campo,
escreve `ativo: true` (preservando o comportamento anterior).

Flags:
  --dry-run   (padrão) Lista o que seria feito, sem gravar nada.
  --apply     Executa as alterações no Firestore.

Idempotente: docs que já têm `ativo` (true ou false) são pulados.

Uso:
  python scripts/migrations/migrar_usuarios_ativo.py           # dry-run
  python scripts/migrations/migrar_usuarios_ativo.py --apply   # executa
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import firebase_admin  # noqa: E402
from firebase_admin import credentials, firestore  # noqa: E402

from scripts.migrations._migration_utils import _commit_batch, _iter_collection_paginated  # noqa: E402


def _init_firebase() -> None:
    try:
        firebase_admin.get_app()
    except ValueError:
        cred_path = os.path.join(ROOT, "credentials.json")
        if not os.path.exists(cred_path):
            raise FileNotFoundError(f"credentials.json não encontrado em: {cred_path}") from None
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)


def migrar(db, dry_run: bool) -> dict:
    prefix = "[DRY-RUN]" if dry_run else "[APPLY]"
    processados = 0
    atualizados = 0
    pulados = 0
    pending: list = []

    print("\n=== usuarios — backfill campo ativo ===")

    for doc in _iter_collection_paginated(db.collection("usuarios")):
        processados += 1
        data = doc.to_dict()
        email = data.get("email", doc.id)

        if "ativo" in data:
            print(f"  [SKIP] '{email}' — campo ativo já existe: {data['ativo']}")
            pulados += 1
            continue

        print(f"  {prefix} '{email}' (doc={doc.id}) -- sem campo ativo -> set ativo=true")
        if not dry_run:
            pending.append((doc.reference, {"ativo": True}))
        atualizados += 1

    if not dry_run and pending:
        _commit_batch(db, pending)

    stats = {"processados": processados, "atualizados": atualizados, "pulados": pulados}
    print(f"\n  Processados: {processados} | Atualizados: {atualizados} | Pulados: {pulados}")
    return stats


def main() -> None:
    dry_run = "--apply" not in sys.argv

    print("=" * 60)
    print(f"  migrar_usuarios_ativo.py  |  modo: {'DRY-RUN' if dry_run else 'APPLY'}")
    print("=" * 60)

    if dry_run:
        print("\n  Use --apply para executar as alterações no Firestore.")

    _init_firebase()
    db = firestore.client()

    migrar(db, dry_run)

    print(
        "\n=== Concluído"
        + (" (nenhuma alteração gravada)" if dry_run else " (alterações gravadas)")
        + " ==="
    )


if __name__ == "__main__":
    main()
