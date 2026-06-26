"""
Adiciona o setor "TI" ao Firestore (categorias_setores) se ainda não existir.

Idempotente: pode ser rodado múltiplas vezes sem efeitos colaterais.
Dry-run por padrão; use --apply para gravar de verdade.

Uso:
    python scripts/adicionar_setor_ti.py            # inspeciona sem gravar
    python scripts/adicionar_setor_ti.py --apply    # grava no Firestore
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

NOME_PT = "TI"
NOME_EN = "IT"
NOME_ES = "TI"
DESCRICAO_PT = "Departamento de tecnologia da informação"
DESCRICAO_EN = "Information Technology department"
DESCRICAO_ES = "Departamento de tecnología de la información"


def _init_firebase():
    import firebase_admin
    from firebase_admin import credentials, firestore

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
    return firestore.client()


def run(apply: bool) -> None:
    db = _init_firebase()
    col = db.collection("categorias_setores")

    todos = [(doc.id, doc.to_dict()) for doc in col.stream()]
    existentes = [(doc_id, data) for doc_id, data in todos if data.get("nome_pt") == NOME_PT]

    if existentes:
        doc_id, data = existentes[0]
        if data.get("ativo") is True:
            print(
                f"[INFO] Setor '{NOME_PT}' já existe e está ativo (doc_id={doc_id}). Nada a fazer."
            )
            return
        # Existe mas inativo — ativar
        if apply:
            col.document(doc_id).update({"ativo": True})
            print(f"[OK] Setor '{NOME_PT}' ativado (doc_id={doc_id})")
        else:
            print(f"[DRY-RUN] Setor '{NOME_PT}' existe mas está inativo (doc_id={doc_id})")
            print("  Acao: atualizaria ativo=False -> ativo=True")
            print("\nNenhuma alteração foi feita. Use --apply para gravar.")
        return

    payload = {
        "nome_pt": NOME_PT,
        "nome_en": NOME_EN,
        "nome_es": NOME_ES,
        "descricao_pt": DESCRICAO_PT,
        "descricao_en": DESCRICAO_EN,
        "descricao_es": DESCRICAO_ES,
        "ativo": True,
        "data_criacao": datetime.now(),
    }

    if apply:
        doc_ref = col.add(payload)[1]
        print(f"[OK] Setor '{NOME_PT}' criado (doc_id={doc_ref.id})")
    else:
        print(f"[DRY-RUN] Criaria setor '{NOME_PT}' com payload:")
        for k, v in payload.items():
            print(f"  {k}: {v!r}")
        print("\nNenhuma alteração foi feita. Use --apply para gravar.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Efetua alterações reais no Firestore (padrão: dry-run)",
    )
    args = parser.parse_args()

    if args.apply:
        print("[AVISO] Modo APPLY — alterações SERÃO gravadas no Firestore.")
    else:
        print("[INFO] Modo DRY-RUN — nenhuma alteração será gravada.")

    run(args.apply)
