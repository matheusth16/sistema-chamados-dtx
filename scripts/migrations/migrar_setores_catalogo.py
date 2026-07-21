"""
Migração suave dos setores: renomear PPCP, unificar Procurement→Compras,
desativar subsetores de Produção, corrigir acentuação de Logistica.

Flags:
  --dry-run   (padrão) Apenas lista o que seria feito, sem gravar nada.
  --apply     Executa as alterações no Firestore.

Requer credentials.json na raiz do projeto.

Coleções afetadas:
  categorias_setores — rename + desativação
  chamados           — migra campo `area` e `setores_adicionais`
  usuarios           — migra campo `areas` (lista)

NÃO altera nenhuma referência aos subsetores Produção - *
NÃO executa scripts/migrations/atualizar_setores_from_print.py
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import firebase_admin  # noqa: E402, I001
from firebase_admin import credentials, firestore  # noqa: E402
from scripts.migrations._migration_utils import (  # noqa: E402
    _commit_batch,
    _iter_collection_paginated,
    _write_checkpoint as _write_checkpoint_util,
)

CHECKPOINT_DIR = Path(ROOT) / "scripts" / ".checkpoints"

# ---------------------------------------------------------------------------
# Mapeamento de migração de nome de setor (chave antiga → nome_pt novo)
# ---------------------------------------------------------------------------
RENAME_MAP: dict[str, str] = {
    "PPCP": "Planejamento de Produção",
    "Logistica": "Logística",
    "Procurement": "Compras",
}

# Setores a desativar (ativo=False) no catálogo
DESATIVAR: set[str] = {
    "Produção - Usinagem",
    "Produção - Montagem",
    "Produção - Inspeções",
    "Produção - Processos Especiais",
}

# Setores que devem existir no catálogo (criados se ausentes)
GARANTIR: list[dict] = [
    {
        "nome_pt": "Compras",
        "nome_en": "Procurement",
        "nome_es": "Aprovisionamiento",
    },
    {
        "nome_pt": "Logística",
        "nome_en": "Logistics",
        "nome_es": "Logística",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_firebase() -> None:
    try:
        firebase_admin.get_app()
    except ValueError:
        cred_path = os.path.join(ROOT, "credentials.json")
        if not os.path.exists(cred_path):
            raise FileNotFoundError(  # noqa: B904
                f"credentials.json não encontrado em: {cred_path}"
            )
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)


def _prefix(dry_run: bool) -> str:
    return "[DRY-RUN]" if dry_run else "[APPLY]"


def _write_checkpoint(checkpoint_dir: Path, fase: str, stats: dict) -> None:
    """Grava checkpoint JSON após fase concluída com --apply."""
    _write_checkpoint_util(checkpoint_dir, "migrar_setores", fase, stats)


def _rename_nome_en_es(nome_pt: str) -> dict:
    """Retorna nome_en e nome_es para o novo nome canônico."""
    from app.services.translation_service import traduzir_categoria

    t = traduzir_categoria(nome_pt)
    return {"nome_en": t.get("en") or nome_pt, "nome_es": t.get("es") or nome_pt}


# ---------------------------------------------------------------------------
# Fase A: categorias_setores
# ---------------------------------------------------------------------------


def migrar_catalogo(db, dry_run: bool, checkpoint_dir: Path | None = None) -> dict:
    print("\n=== categorias_setores ===")
    p = _prefix(dry_run)
    nomes_existentes: set[str] = set()
    stats: dict = {"renomeados": 0, "desativados": 0, "criados": 0}
    pending: list = []

    for doc in db.collection("categorias_setores").stream():
        data = doc.to_dict()
        nome_pt = data.get("nome_pt", "")
        nomes_existentes.add(nome_pt)

        # Rename
        if nome_pt in RENAME_MAP:
            novo = RENAME_MAP[nome_pt]
            traducoes = _rename_nome_en_es(novo)
            payload = {"nome_pt": novo, **traducoes}
            print(f"  {p} RENAME '{nome_pt}' -> '{novo}' (doc={doc.id})")
            if not dry_run:
                pending.append((doc.reference, payload))
                stats["renomeados"] += 1
            nomes_existentes.discard(nome_pt)
            nomes_existentes.add(novo)

        # Desativar
        if nome_pt in DESATIVAR:
            if data.get("ativo", True):
                print(f"  {p} DESATIVAR '{nome_pt}' (doc={doc.id})")
                if not dry_run:
                    pending.append((doc.reference, {"ativo": False}))
                    stats["desativados"] += 1
            else:
                print(f"  [SKIP] '{nome_pt}' já está inativo")

    if not dry_run and pending:
        _commit_batch(db, pending)

    # Garantir setores obrigatórios existem
    for setor in GARANTIR:
        nome = setor["nome_pt"]
        if nome not in nomes_existentes:
            print(f"  {p} CRIAR setor ausente '{nome}'")
            if not dry_run:
                db.collection("categorias_setores").add(
                    {
                        **setor,
                        "ativo": True,
                        "data_criacao": datetime.now(UTC),
                    }
                )
                stats["criados"] += 1
        else:
            print(f"  [OK] '{nome}' já existe no catálogo")

    if not dry_run and checkpoint_dir is not None:
        _write_checkpoint(checkpoint_dir, "catalogo", stats)
    return stats


# ---------------------------------------------------------------------------
# Fase B: chamados — campos `area` e `setores_adicionais`
# ---------------------------------------------------------------------------


def _migrate_setor_value(valor: str) -> str | None:
    """Retorna novo valor se necessário migrar, else None."""
    return RENAME_MAP.get(valor)


def migrar_chamados(db, dry_run: bool, checkpoint_dir: Path | None = None) -> dict:
    print("\n=== chamados ===")
    p = _prefix(dry_run)
    processados = 0
    alterados = 0
    pending: list = []

    for doc in _iter_collection_paginated(db.collection("chamados")):
        processados += 1
        data = doc.to_dict()
        updates: dict = {}

        # Campo `area`
        area = data.get("area", "")
        novo_area = _migrate_setor_value(area)
        if novo_area:
            updates["area"] = novo_area

        # Campo `setores_adicionais` (string separada por vírgula ou lista)
        sa = data.get("setores_adicionais")
        if sa:
            if isinstance(sa, list):
                novos = [RENAME_MAP.get(s, s) for s in sa]
                if novos != sa:
                    updates["setores_adicionais"] = novos
            elif isinstance(sa, str):
                partes = [s.strip() for s in sa.split(",")]
                novos = [RENAME_MAP.get(s, s) for s in partes]
                novo_str = ", ".join(novos)
                if novo_str != sa:
                    updates["setores_adicionais"] = novo_str

        if updates:
            print(f"  {p} chamado doc={doc.id}: {updates}")
            if not dry_run:
                pending.append((doc.reference, updates))
            alterados += 1

    if not dry_run and pending:
        _commit_batch(db, pending)

    stats = {"processados": processados, "alterados": alterados}
    print(f"  Total chamados com alteração: {alterados}")

    if not dry_run and checkpoint_dir is not None:
        _write_checkpoint(checkpoint_dir, "chamados", stats)
    return stats


# ---------------------------------------------------------------------------
# Fase C: usuarios — campo `areas` (lista)
# ---------------------------------------------------------------------------


def migrar_usuarios(db, dry_run: bool, checkpoint_dir: Path | None = None) -> dict:
    print("\n=== usuarios ===")
    p = _prefix(dry_run)
    processados = 0
    alterados = 0
    pending: list = []

    for doc in _iter_collection_paginated(db.collection("usuarios")):
        processados += 1
        data = doc.to_dict()
        updates: dict = {}

        # Campo `areas` (lista)
        areas = data.get("areas", [])
        if isinstance(areas, list):
            novas = [RENAME_MAP.get(a, a) for a in areas]
            if novas != areas:
                updates["areas"] = novas

        # Campo `area` legado (string)
        area_legado = data.get("area", "")
        if area_legado and area_legado in RENAME_MAP:
            updates["area"] = RENAME_MAP[area_legado]

        if updates:
            email = data.get("email", doc.id)
            print(f"  {p} usuario '{email}': {updates}")
            if not dry_run:
                pending.append((doc.reference, updates))
            alterados += 1

    if not dry_run and pending:
        _commit_batch(db, pending)

    stats = {"processados": processados, "alterados": alterados}
    print(f"  Total usuarios com alteração: {alterados}")

    if not dry_run and checkpoint_dir is not None:
        _write_checkpoint(checkpoint_dir, "usuarios", stats)
    return stats


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    dry_run = "--apply" not in sys.argv
    checkpoint_dir = CHECKPOINT_DIR if not dry_run else None

    print("=" * 60)
    print(f"  migrar_setores_catalogo.py  |  modo: {'DRY-RUN' if dry_run else 'APPLY'}")
    print("=" * 60)

    if dry_run:
        print("\n  Use --apply para executar as alterações no Firestore.")

    _init_firebase()
    db = firestore.client()

    migrar_catalogo(db, dry_run, checkpoint_dir=checkpoint_dir)
    migrar_chamados(db, dry_run, checkpoint_dir=checkpoint_dir)
    migrar_usuarios(db, dry_run, checkpoint_dir=checkpoint_dir)

    print(
        "\n=== Concluído"
        + (" (nenhuma alteração gravada)" if dry_run else " (alterações gravadas)")
        + " ==="
    )
    if checkpoint_dir:
        print(f"  Checkpoints em: {checkpoint_dir}")


if __name__ == "__main__":
    main()
