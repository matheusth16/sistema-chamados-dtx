"""Semeia o documento config/setor_para_area no Firestore.

Grava o mapeamento inicial de setor → área para que utils_areas.py use o
Firestore como fonte de verdade em vez do dict hardcoded (F-30).

Por padrão roda em modo dry-run: mostra o que seria gravado sem escrever.

Uso:
    python scripts/migrations/migrar_setor_area.py          # dry-run (mostra payload)
    python scripts/migrations/migrar_setor_area.py --apply  # grava no Firestore
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_CHECKPOINT_DIR = Path(__file__).resolve().parent.parent / ".checkpoints"

MAPA_INICIAL = {
    "Material Indireto / Compras": "Material",
    "Manutenção": "Manutencao",
}


def executar(db, dry_run: bool = True, checkpoint_dir: Path = _CHECKPOINT_DIR) -> dict:
    """Grava (ou simula) config/setor_para_area no Firestore.

    Retorna stats: {"gravado": bool, "entradas": int, "dry_run": bool}.
    """
    print("Payload a ser gravado:")
    print("  Coleção  : config")
    print("  Documento: setor_para_area")
    print(f"  Campos   : mapa = {MAPA_INICIAL}")

    if dry_run:
        logger.info("Modo DRY-RUN — nenhum dado será gravado no Firestore.")
        print("\n[DRY-RUN] Nenhuma escrita realizada. Use --apply para gravar.")
        return {"gravado": False, "entradas": len(MAPA_INICIAL), "dry_run": True}

    ref = db.collection("config").document("setor_para_area")
    ref.set({"mapa": MAPA_INICIAL})
    logger.info("Documento config/setor_para_area gravado com sucesso.")

    from scripts.migrations._migration_utils import _write_checkpoint

    _write_checkpoint(
        checkpoint_dir,
        "migrar_setor_area",
        "gravar_mapa",
        {"entradas": len(MAPA_INICIAL), "dry_run": False},
    )
    print("\nMigração concluída. Checkpoint gravado.")
    return {"gravado": True, "entradas": len(MAPA_INICIAL), "dry_run": False}


def main():
    parser = argparse.ArgumentParser(
        description="Semeia config/setor_para_area no Firestore (F-30)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Grava o documento (padrão: dry-run)",
    )
    args = parser.parse_args()

    from app import create_app

    app = create_app()
    with app.app_context():
        from app.database import db

        executar(db, dry_run=not args.apply)


if __name__ == "__main__":
    main()
