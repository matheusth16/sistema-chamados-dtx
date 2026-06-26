"""
Migração: preenche o campo supervisor_ids_com_acesso em chamados existentes.

O campo desnormalizado é necessário para a query de dashboard isolada por supervisor
(Fase 2 — Escalonamento SLA, ADR-004). Chamados criados antes desta fase não possuem
o campo, o que impede que supervisores os vejam no dashboard após a deploy.

Regras de cálculo (mesmas de calcular_supervisor_ids_com_acesso em permissions.py):
  - Com responsavel_id: [responsavel_id] + participantes[*].supervisor_id
  - Sem responsavel_id (fila): todos supervisores/admins da área + participantes

Flags:
  --dry-run  (padrão) Lista o que seria atualizado, sem gravar nada.
  --apply    Executa as alterações no Firestore em batches de 500.

Uso:
  python scripts/migrar_supervisor_ids_com_acesso.py --dry-run
  python scripts/migrar_supervisor_ids_com_acesso.py --apply
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import firebase_admin  # noqa: E402, I001
from firebase_admin import credentials, firestore as fs  # noqa: E402
from scripts._migration_utils import (  # noqa: E402
    _commit_batch,
    _iter_collection_paginated,
    _write_checkpoint,
)

CHECKPOINT_DIR = Path(ROOT) / "scripts" / ".checkpoints"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _calcular_ids(data: dict, supervisores_por_area: dict[str, list[str]]) -> list[str]:
    """Calcula supervisor_ids_com_acesso para um documento de chamado."""
    ids: set[str] = set()
    participantes = data.get("participantes") or []
    for p in participantes:
        if isinstance(p, dict) and p.get("supervisor_id"):
            ids.add(p["supervisor_id"])

    responsavel_id = data.get("responsavel_id")
    if responsavel_id:
        ids.add(responsavel_id)
    else:
        area = data.get("area", "")
        for sup_id in supervisores_por_area.get(area, []):
            ids.add(sup_id)

    return sorted(ids)


def _carregar_supervisores_por_area(db) -> dict[str, list[str]]:
    """Mapa área → [id, ...] de supervisores/admins. Uma query full-scan nos usuários."""
    mapa: dict[str, list[str]] = {}
    for doc in db.collection("usuarios").stream():
        u = doc.to_dict()
        if u.get("perfil") not in ("supervisor", "admin"):
            continue
        for area in u.get("areas", []):
            mapa.setdefault(area, []).append(doc.id)
    return mapa


# ---------------------------------------------------------------------------
# Função principal de migração
# ---------------------------------------------------------------------------


def migrar_supervisor_ids(db, dry_run: bool = True) -> dict:
    """Backfill supervisor_ids_com_acesso em chamados sem o campo.

    Returns:
        dict com stats: total_verificados, total_atualizados, total_ja_ok
    """
    supervisores_por_area = _carregar_supervisores_por_area(db)

    stats = {"total_verificados": 0, "total_atualizados": 0, "total_ja_ok": 0}
    pending: list = []

    for doc in _iter_collection_paginated(db.collection("chamados")):
        stats["total_verificados"] += 1
        data = doc.to_dict()

        ids_atuais = data.get("supervisor_ids_com_acesso")
        novos_ids = _calcular_ids(data, supervisores_por_area)

        if ids_atuais == novos_ids:
            stats["total_ja_ok"] += 1
            continue

        stats["total_atualizados"] += 1
        if dry_run:
            print(
                f"  [dry-run] {doc.id[:8]}… | área={data.get('area')} "
                f"| resp={data.get('responsavel_id')} → ids={novos_ids}"
            )
        else:
            pending.append((doc.reference, {"supervisor_ids_com_acesso": novos_ids}))

    if not dry_run and pending:
        _commit_batch(db, pending)
        _write_checkpoint(
            CHECKPOINT_DIR,
            "migrar_supervisor_ids_com_acesso",
            "backfill",
            stats,
        )

    return stats


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main():
    args = sys.argv[1:]
    dry_run = "--apply" not in args

    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"=== migrar_supervisor_ids_com_acesso — modo {mode} ===")

    cred_path = Path(ROOT) / "credentials.json"
    if not firebase_admin._apps:
        if cred_path.exists():
            cred = credentials.Certificate(str(cred_path))
        else:
            cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)

    db = fs.client()
    stats = migrar_supervisor_ids(db, dry_run=dry_run)

    print(
        f"\nResumo: verificados={stats['total_verificados']} | "
        f"atualizados={stats['total_atualizados']} | já_ok={stats['total_ja_ok']}"
    )
    if dry_run:
        print("\nNenhuma alteração gravada. Use --apply para executar.")
    else:
        print("\nMigração concluída.")


if __name__ == "__main__":
    main()
