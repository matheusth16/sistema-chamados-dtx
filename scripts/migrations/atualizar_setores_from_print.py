"""
One-shot: resetar `categorias_setores` e recriar a lista final de setores.

Objetivo (conforme solicitado):
- Retirar tudo que existe hoje.
- Manter apenas: `Engenharia` e `Qualidade`.
- Adicionar os demais departamentos do print, EXCETO:
  `NDT`, `MACHINING`, `ASSEMBLY`, `INSPECTION`.

ATENÇÃO: Este script APAGA a coleção `categorias_setores` por completo e a
recria. Por padrão executa em modo DRY-RUN (somente leitura). Use --apply
para efetuar as alterações reais.

Uso:
    python scripts/migrations/atualizar_setores_from_print.py            # dry-run (seguro)
    python scripts/migrations/atualizar_setores_from_print.py --apply    # grava de verdade

Requer `credentials.json` na raiz do projeto.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, firestore

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, ROOT)


def _init_firebase():
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


def _delete_all(collection_name: str, apply: bool) -> None:
    ref = db.collection(collection_name)
    deletados = 0
    for doc in ref.stream():
        if apply:
            doc.reference.delete()
            print(f"  Deletado setor doc_id={doc.id}")
        else:
            print(f"  [DRY-RUN] Deletaria setor doc_id={doc.id}")
        deletados += 1
    rotulo = "Total deletados" if apply else "Total que seria deletado"
    print(f"{rotulo} em `{collection_name}`: {deletados}")


def _upsert_sectors(
    sectors: Iterable[dict],
    apply: bool,
) -> None:
    ts = datetime.now()
    count = 0
    for s in sectors:
        payload = {
            "nome_pt": s["nome_pt"],
            "nome_en": s.get("nome_en") or s["nome_pt"],
            "nome_es": s.get("nome_es") or s["nome_pt"],
            "descricao_pt": s.get("descricao_pt"),
            "descricao_en": s.get("descricao_en"),
            "descricao_es": s.get("descricao_es"),
            "ativo": bool(s.get("ativo", True)),
            "data_criacao": ts,
        }
        if apply:
            doc = db.collection("categorias_setores").add(payload)[1]
            print(f"[OK] Setor '{payload['nome_pt']}' criado (doc_id={doc.id})")
        else:
            print(f"  [DRY-RUN] Criaria setor '{payload['nome_pt']}'")
        count += 1
    rotulo = "Total criados" if apply else "Total que seria criado"
    print(f"{rotulo} em `categorias_setores`: {count}")


if __name__ == "__main__":
    from app.services.translation_service import traduzir_categoria

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Efetua alterações reais no Firestore (padrão: dry-run)",
    )
    args = parser.parse_args()

    if args.apply:
        print("[AVISO] Modo APPLY ativo — alterações SERÃO gravadas no Firestore.")
    else:
        print("[INFO] Modo DRY-RUN — nenhuma alteração será gravada. Use --apply para gravar.")

    _init_firebase()
    db = firestore.client()

    print("Resetando `categorias_setores` (somente setores) ...")
    _delete_all("categorias_setores", args.apply)

    # Lista final validada (mantém Engenharia/Qualidade e adiciona do print).
    # Exclui explicitamente: NDT, MACHINING, ASSEMBLY, INSPECTION.
    setores_final = [
        "Engenharia",
        "Qualidade",
        "PPCP",
        "TI",
        "Commercial",
        "Suprimentos",
        "Planejamento Materiais",
        "Logistica",
        "Infraestrutura",
        "RH",
        "Produção - Montagem",
        "Produção - Usinagem",
        "Produção - Inspeções",
        "Produção - Processos Especiais",
        "Procurement",
    ]

    # Monta payloads compatíveis com `CategoriaSetor`.
    payloads = []
    for nome_pt in setores_final:
        t = traduzir_categoria(nome_pt)
        payloads.append(
            {
                "nome_pt": nome_pt,
                "nome_en": t.get("en") or nome_pt,
                "nome_es": t.get("es") or nome_pt,
                "ativo": True,
            }
        )

    print("\nCriando setores finais ...")
    _upsert_sectors(payloads, args.apply)

    if args.apply:
        print("\nConcluído.")
    else:
        print("\nDry-run concluído. Nenhuma alteração foi feita. Use --apply para executar.")
