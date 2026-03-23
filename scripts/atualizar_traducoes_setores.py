"""
One-shot: atualizar `nome_en` e `nome_es` nos documentos existentes de `categorias_setores`.

Não apaga nada — apenas faz patch nos campos de tradução usando o TRANSLATION_MAP atualizado.

Requer `credentials.json` na raiz do projeto.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import firebase_admin  # noqa: E402
from firebase_admin import credentials, firestore  # noqa: E402

from app.services.translation_service import traduzir_categoria  # noqa: E402


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


if __name__ == "__main__":
    _init_firebase()
    db = firestore.client()

    docs = list(db.collection("categorias_setores").stream())
    print(f"Encontrados {len(docs)} setores.\n")

    atualizados = 0
    sem_traducao = []

    for doc in docs:
        data = doc.to_dict()
        nome_pt = data.get("nome_pt", "")
        if not nome_pt:
            print(f"  [SKIP] doc_id={doc.id} sem nome_pt")
            continue

        t = traduzir_categoria(nome_pt)
        nome_en = t.get("en") or nome_pt
        nome_es = t.get("es") or nome_pt

        if nome_en == nome_pt and nome_es == nome_pt:
            sem_traducao.append(nome_pt)

        doc.reference.update({"nome_en": nome_en, "nome_es": nome_es})
        print(f"  [OK] '{nome_pt}' => EN: '{nome_en}' | ES: '{nome_es}'")
        atualizados += 1

    print(f"\nTotal atualizados: {atualizados}")

    if sem_traducao:
        print("\n[AVISO] Setores sem traducao no mapa (usaram nome_pt como fallback):")
        for nome in sem_traducao:
            print(f"   - {nome}")
        print("   -> Adicione-os manualmente em app/services/translation_service.py")
    else:
        print("\n✓ Todos os setores foram traduzidos com sucesso.")
