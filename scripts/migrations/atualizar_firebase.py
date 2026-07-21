"""
OBSOLETO: Este script foi substituído por scripts/migrations/migrar_setores_catalogo.py
(que possui flag --dry-run e é idempotente). Mantido apenas para referência
histórica. Não executar em produção sem revisar o código.

ATENÇÃO: Este script APAGA as coleções `categorias_setores` e
`categorias_impactos` por completo e as recria. Por padrão executa em modo
DRY-RUN (somente leitura, nenhuma alteração é gravada). Use --apply para
efetuar as alterações reais.

Uso:
    python scripts/migrations/atualizar_firebase.py            # dry-run (seguro)
    python scripts/migrations/atualizar_firebase.py --apply    # grava de verdade
"""

import argparse
import os
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, firestore

# Garante que credentials.json seja encontrado na raiz do projeto
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)


# Setores EXATOS do formulário
SETORES_DADOS = [
    {
        "nome_pt": "Manutenção",
        "nome_en": "Maintenance",
        "nome_es": "Mantenimiento",
        "ativo": True,
    },
    {
        "nome_pt": "Engenharia",
        "nome_en": "Engineering",
        "nome_es": "Ingeniería",
        "ativo": True,
    },
    {
        "nome_pt": "Qualidade",
        "nome_en": "Quality",
        "nome_es": "Calidad",
        "ativo": True,
    },
    {
        "nome_pt": "Comercial",
        "nome_en": "Commercial",
        "nome_es": "Comercial",
        "ativo": True,
    },
    {
        "nome_pt": "Planejamento",
        "nome_en": "Planning",
        "nome_es": "Planificación",
        "ativo": True,
    },
    {
        "nome_pt": "Material Indireto / Compras",
        "nome_en": "Indirect Material / Procurement",
        "nome_es": "Material Indirecto / Compras",
        "ativo": True,
    },
]

# Impactos EXATOS do formulário
IMPACTOS_DADOS = [
    {
        "nome_pt": "Prazo / Cliente",
        "nome_en": "Deadline / Customer",
        "nome_es": "Plazo / Cliente",
        "ativo": True,
    },
    {
        "nome_pt": "Qualidade",
        "nome_en": "Quality",
        "nome_es": "Calidad",
        "ativo": True,
    },
    {
        "nome_pt": "Segurança",
        "nome_en": "Safety",
        "nome_es": "Seguridad",
        "ativo": True,
    },
]


def _init_firebase():
    try:
        firebase_admin.get_app()
    except ValueError:
        cred = credentials.Certificate(os.path.join(ROOT, "credentials.json"))
        firebase_admin.initialize_app(cred)


def _limpar_colecao(db, nome_colecao: str, apply: bool) -> None:
    for doc in db.collection(nome_colecao).stream():
        if apply:
            db.collection(nome_colecao).document(doc.id).delete()
            print(f"  Deletado {nome_colecao}: {doc.id}")
        else:
            print(f"  [DRY-RUN] Deletaria {nome_colecao}: {doc.id}")


def _criar_documentos(db, nome_colecao: str, dados: list[dict], rotulo: str, apply: bool) -> None:
    for item in dados:
        if apply:
            payload = {**item, "criado_em": datetime.now()}
            db.collection(nome_colecao).add(payload)
            print(f"[OK] {rotulo} '{item['nome_pt']}' criado")
        else:
            print(f"  [DRY-RUN] Criaria {rotulo} '{item['nome_pt']}'")


def main() -> None:
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

    print("\nLimpando categorias antigas...")
    _limpar_colecao(db, "categorias_setores", args.apply)
    _limpar_colecao(db, "categorias_impactos", args.apply)

    print("\nCriando novos setores...")
    _criar_documentos(db, "categorias_setores", SETORES_DADOS, "Setor", args.apply)

    print("\nCriando novos impactos...")
    _criar_documentos(db, "categorias_impactos", IMPACTOS_DADOS, "Impacto", args.apply)

    if args.apply:
        print("\nFirebase atualizado com sucesso!")
    else:
        print("\nDry-run concluído. Nenhuma alteração foi feita. Use --apply para executar.")
    print("Total: 6 setores + 3 impactos")


if __name__ == "__main__":
    main()
