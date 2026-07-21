"""Utilitários compartilhados entre scripts de migração."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def _commit_batch(db, pending: list, chunk_size: int = 500) -> None:
    """Commit (ref, updates) pairs using Firestore batch.update (≤500 ops each)."""
    for i in range(0, len(pending), chunk_size):
        batch = db.batch()
        for ref, data in pending[i : i + chunk_size]:
            batch.update(ref, data)
        batch.commit()


def _commit_batch_set(db, pending: list, chunk_size: int = 500) -> None:
    """Commit (ref, data) pairs using Firestore batch.set — creates new documents."""
    for i in range(0, len(pending), chunk_size):
        batch = db.batch()
        for ref, data in pending[i : i + chunk_size]:
            batch.set(ref, data)
        batch.commit()


def _iter_collection_paginated(collection_ref, page_size: int = 500):
    """Iterate a Firestore collection using cursor-based pagination (no full list() in memory)."""
    last_doc = None
    while True:
        if last_doc is None:
            query = collection_ref.limit(page_size)
        else:
            query = collection_ref.limit(page_size).start_after(last_doc)
        count = 0
        for doc in query.stream():
            count += 1
            last_doc = doc
            yield doc
        if count < page_size:
            break


def _write_checkpoint(checkpoint_dir: Path, script_name: str, fase: str, stats: dict) -> None:
    """Grava checkpoint JSON após fase concluída com --apply."""
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = checkpoint_dir / f"{script_name}_{ts}_{fase}.json"
    payload = {
        "fase": fase,
        "concluida_em": datetime.now(UTC).isoformat(),
        "stats": stats,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Checkpoint gravado: {path}")
