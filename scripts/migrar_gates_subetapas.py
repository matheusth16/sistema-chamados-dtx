"""
Migração idempotente: popula categorias_gates no Firestore com as 16 sub-etapas padrão.

Flags:
  --dry-run   (padrão) Lista o que seria criado, sem gravar nada.
  --apply     Executa as inserções no Firestore.

Execução (da raiz do projeto):
    python scripts/migrar_gates_subetapas.py          # dry-run
    python scripts/migrar_gates_subetapas.py --apply  # aplica

Características:
- Não duplica: verifica por nome_pt antes de criar.
- Não sobrescreve: gates existentes com mesmo nome_pt são ignorados.
- Gates legados flat (ex: 'Gate 1' sem gate_pai) são listados mas NÃO removidos.
"""

import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

from app.database import db  # noqa: E402
from app.gates_config import GATE_SUBETAPAS  # noqa: E402
from app.models_categorias import CategoriaGate  # noqa: E402
from scripts._migration_utils import _commit_batch_set, _write_checkpoint  # noqa: E402

_CHECKPOINT_DIR = Path(ROOT) / "scripts" / ".checkpoints"


def migrar(dry_run: bool = True, checkpoint_dir: Path | None = None) -> dict:
    p = "[DRY-RUN]" if dry_run else "[APPLY]"
    print("=" * 60)
    print(f"MIGRACAO: gates sub-etapas -> Firestore  |  modo: {'DRY-RUN' if dry_run else 'APPLY'}")
    print("=" * 60)

    if dry_run:
        print("\n  Use --apply para executar as alterações no Firestore.\n")

    gates_existentes = CategoriaGate.get_all()
    nomes_existentes = {g.nome_pt for g in gates_existentes if g.nome_pt}

    # Avisar sobre gates legados sem gate_pai
    legados = [g for g in gates_existentes if not g.gate_pai]
    if legados:
        print(f"\n  {len(legados)} gate(s) legado(s) sem gate_pai encontrado(s):")
        for g in legados:
            print(f"   ID={g.id}  nome_pt='{g.nome_pt}'")
        print("   -> Esses gates NAO aparecem no formulario de Novo Chamado.")
        print("   -> Voce pode excluí-los manualmente no admin se nao forem mais usados.\n")

    criados = 0
    ignorados = 0
    pending: list = []

    for gate_pai, etapas in GATE_SUBETAPAS.items():
        for ordem_local, nome_pt in enumerate(etapas, start=1):
            if nome_pt in nomes_existentes:
                print(f"  Ja existe: '{nome_pt}'")
                ignorados += 1
                continue

            etapa = nome_pt.replace(f"{gate_pai} - ", "", 1)
            gate = CategoriaGate(
                nome_pt=nome_pt,
                descricao_pt="",
                gate_pai=gate_pai,
                etapa=etapa,
                ordem=ordem_local,
                ativo=True,
            )
            print(f"  {p} Criar: '{nome_pt}' (gate_pai={gate_pai}, ordem={ordem_local})")
            if not dry_run:
                ref = db.collection("categorias_gates").document()
                pending.append((ref, gate.to_dict()))
            criados += 1

    if not dry_run and pending:
        _commit_batch_set(db, pending)

    stats = {"criados": criados, "ignorados": ignorados}

    print(f"\n{'=' * 60}")
    if dry_run:
        print(f"DRY-RUN: {criados} gate(s) seriam criados, {ignorados} ja existiam.")
    else:
        print(f"Concluido: {criados} criado(s), {ignorados} ignorado(s) (ja existiam).")
    print("=" * 60)

    if not dry_run and checkpoint_dir is not None:
        _write_checkpoint(checkpoint_dir, "migrar_gates", "gates", stats)

    return stats


if __name__ == "__main__":
    dry_run = "--apply" not in sys.argv
    migrar(dry_run=dry_run, checkpoint_dir=_CHECKPOINT_DIR if not dry_run else None)
