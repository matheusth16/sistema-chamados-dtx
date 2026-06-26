"""
Migração: converte setores_adicionais → participantes[] estruturados (Fase 4, ADR-004).

Para cada chamado com setores_adicionais não vazio e participantes[] vazio:
  - Para cada setor: resolve o primeiro supervisor ativo da área.
  - Cria entrada {supervisor_id, area, status: 'pendente', concluido_em: None}.
  - Recalcula supervisor_ids_com_acesso.

Idempotente: pula chamados que já possuem participantes[] populado.

Flags:
  --dry-run  (padrão) Lista o que seria alterado, sem gravar nada.
  --apply    Executa as alterações no Firestore em batches de 500.

Uso:
  python scripts/migrar_participantes.py --dry-run
  python scripts/migrar_participantes.py --apply
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


def _carregar_supervisores_por_area(db) -> dict[str, list[dict]]:
    """Mapa área → [{id, nome}, ...] de supervisores/admins ativos. Query direta no Firestore."""
    mapa: dict[str, list[dict]] = {}
    for doc in db.collection("usuarios").stream():
        u = doc.to_dict()
        if u.get("perfil") not in ("supervisor", "admin"):
            continue
        if not u.get("ativo", True):
            continue
        for area in u.get("areas", []) or []:
            mapa.setdefault(area, []).append({"id": doc.id, "nome": u.get("nome", "")})
    return mapa


def _resolver_supervisor_para_setor(setor: str, supervisores_por_area: dict) -> dict | None:
    """Retorna o primeiro supervisor ativo da área ou None."""
    sups = supervisores_por_area.get(setor, [])
    return sups[0] if sups else None


def _recalcular_supervisor_ids(
    responsavel_id: str | None,
    participantes: list,
    supervisores_por_area: dict,
    area: str,
) -> list[str]:
    """Recalcula supervisor_ids_com_acesso após migração."""
    ids: set[str] = set()
    for p in participantes:
        if isinstance(p, dict) and p.get("supervisor_id"):
            ids.add(p["supervisor_id"])
    if responsavel_id:
        ids.add(responsavel_id)
    else:
        for sup in supervisores_por_area.get(area, []):
            ids.add(sup["id"])
    return sorted(ids)


# ---------------------------------------------------------------------------
# Função principal de migração
# ---------------------------------------------------------------------------


def migrar_participantes(db, dry_run: bool = True) -> dict:
    """Backfill participantes[] a partir de setores_adicionais.

    Returns:
        dict com stats: total_verificados, total_migrados, total_ja_tem_participantes, total_sem_setores, total_sem_supervisor
    """
    supervisores_por_area = _carregar_supervisores_por_area(db)

    stats = {
        "total_verificados": 0,
        "total_migrados": 0,
        "total_ja_tem_participantes": 0,
        "total_sem_setores": 0,
        "total_sem_supervisor": 0,
    }
    pending: list = []

    for doc in _iter_collection_paginated(db.collection("chamados")):
        stats["total_verificados"] += 1
        data = doc.to_dict() or {}

        participantes_atuais = data.get("participantes") or []
        if participantes_atuais:
            stats["total_ja_tem_participantes"] += 1
            continue

        setores_adicionais = data.get("setores_adicionais") or []
        if not setores_adicionais:
            stats["total_sem_setores"] += 1
            continue

        novos_participantes = []
        setor_sem_sup = False
        for setor in setores_adicionais:
            sup = _resolver_supervisor_para_setor(setor, supervisores_por_area)
            if not sup:
                print(
                    f"  [aviso] {doc.id[:8]}… | setor '{setor}' sem supervisor ativo — pulando setor"
                )
                setor_sem_sup = True
                continue
            novos_participantes.append(
                {
                    "supervisor_id": sup["id"],
                    "area": setor,
                    "status": "pendente",
                    "concluido_em": None,
                }
            )

        if not novos_participantes:
            stats["total_sem_supervisor"] += 1
            continue

        if setor_sem_sup:
            stats["total_sem_supervisor"] += 1

        responsavel_id = data.get("responsavel_id")
        area = data.get("area", "")
        novos_ids = _recalcular_supervisor_ids(
            responsavel_id, novos_participantes, supervisores_por_area, area
        )

        stats["total_migrados"] += 1
        if dry_run:
            print(
                f"  [dry-run] {doc.id[:8]}… | área={area} | setores={setores_adicionais} "
                f"→ {len(novos_participantes)} participante(s) | supervisor_ids={novos_ids}"
            )
        else:
            pending.append(
                (
                    doc.reference,
                    {
                        "participantes": novos_participantes,
                        "supervisor_ids_com_acesso": novos_ids,
                    },
                )
            )

    if not dry_run and pending:
        _commit_batch(db, pending)
        _write_checkpoint(
            CHECKPOINT_DIR,
            "migrar_participantes",
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
    print(f"=== migrar_participantes — modo {mode} ===")

    cred_path = Path(ROOT) / "credentials.json"
    if not firebase_admin._apps:
        if cred_path.exists():
            cred = credentials.Certificate(str(cred_path))
        else:
            cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)

    db = fs.client()
    stats = migrar_participantes(db, dry_run=dry_run)

    print(
        f"\nResumo:"
        f"\n  verificados:            {stats['total_verificados']}"
        f"\n  migrados:               {stats['total_migrados']}"
        f"\n  já com participantes:   {stats['total_ja_tem_participantes']}"
        f"\n  sem setores_adicionais: {stats['total_sem_setores']}"
        f"\n  sem supervisor ativo:   {stats['total_sem_supervisor']}"
    )
    if dry_run:
        print("\nNenhuma alteração gravada. Use --apply para executar.")
    else:
        print("\nMigração concluída.")


if __name__ == "__main__":
    main()
