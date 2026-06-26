#!/usr/bin/env python3
"""
Migração de grupos RL:

- Cria documentos na coleção `grupos_rl` a partir dos chamados existentes
  com categoria "Projetos" e campo rl_codigo preenchido.
- Atualiza cada chamado elegível com o campo `grupo_rl_id` correspondente.

Flags:
  --dry-run   (padrão) Lista o que seria feito, sem gravar nada.
  --apply     Executa as alterações no Firestore.

Uso:
    python scripts/migrar_grupos_rl.py          # dry-run
    python scripts/migrar_grupos_rl.py --apply  # aplica
"""

import os
import sys
from pathlib import Path

# Adiciona a raiz do projeto ao path (script está em scripts/)
_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _raiz)

from app.database import db  # noqa: E402
from app.models_grupo_rl import GrupoRL  # noqa: E402
from scripts._migration_utils import (  # noqa: E402
    _commit_batch,
    _iter_collection_paginated,
    _write_checkpoint,
)

_CHECKPOINT_DIR = Path(_raiz) / "scripts" / ".checkpoints"


def migrar_grupos_rl(dry_run: bool = True, checkpoint_dir: Path | None = None) -> None:
    p = "[DRY-RUN]" if dry_run else "[APPLY]"
    print("\n" + "=" * 70)
    print(f"  MIGRACAO - Grupos RL  |  modo: {'DRY-RUN' if dry_run else 'APPLY'}")
    print("=" * 70)

    if dry_run:
        print("\n  Use --apply para executar as alterações no Firestore.\n")

    chamados_ref = db.collection("chamados")

    total = 0
    atualizados = 0
    ignorados_sem_rl = 0
    ignorados_categoria = 0
    ja_com_grupo = 0
    erros = 0
    pending: list = []

    for doc in _iter_collection_paginated(chamados_ref):
        total += 1
        try:
            data = doc.to_dict() or {}
            categoria = data.get("categoria")
            rl_codigo = (data.get("rl_codigo") or "").strip()
            grupo_rl_id_atual = data.get("grupo_rl_id")

            if categoria != "Projetos":
                ignorados_categoria += 1
                continue

            if not rl_codigo:
                ignorados_sem_rl += 1
                continue

            if grupo_rl_id_atual:
                ja_com_grupo += 1
                continue

            grupo = GrupoRL.get_or_create(
                rl_codigo=rl_codigo,
                criado_por_id=data.get("solicitante_id"),
                area=data.get("area"),
            )
            print(f"   {p} Chamado {doc.id} -> grupo_rl_id={grupo.id}")
            if not dry_run:
                pending.append((chamados_ref.document(doc.id), {"grupo_rl_id": grupo.id}))
            atualizados += 1

        except Exception as e:  # pragma: no cover - script de migração
            erros += 1
            print(f"   Erro ao processar chamado {doc.id}: {e}")

    if not dry_run and pending:
        _commit_batch(db, pending)

    stats = {
        "total": total,
        "atualizados": atualizados,
        "ignorados_sem_rl": ignorados_sem_rl,
        "ignorados_categoria": ignorados_categoria,
        "ja_com_grupo": ja_com_grupo,
        "erros": erros,
    }

    print("\n" + "=" * 70)
    print("  RESUMO DA MIGRACAO DE GRUPOS RL")
    print("=" * 70)
    print(f"Total de chamados lidos:         {total}")
    print(f"Chamados categoria 'Projetos':   {total - ignorados_categoria}")
    print(f"  -> Ignorados sem rl_codigo:    {ignorados_sem_rl}")
    print(f"  -> Ja tinham grupo_rl_id:      {ja_com_grupo}")
    print(f"  -> {'Simulados' if dry_run else 'Atualizados'} com grupo_rl_id: {atualizados}")
    print(f"Erros durante processamento:     {erros}")
    print("=" * 70)

    if not dry_run and checkpoint_dir is not None:
        _write_checkpoint(checkpoint_dir, "migrar_grupos_rl", "grupos_rl", stats)


if __name__ == "__main__":  # pragma: no cover - execução direta
    dry_run = "--apply" not in sys.argv
    migrar_grupos_rl(dry_run=dry_run, checkpoint_dir=_CHECKPOINT_DIR if not dry_run else None)
