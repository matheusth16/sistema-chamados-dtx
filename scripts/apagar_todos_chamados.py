"""
Script para apagar TODOS os chamados e o histórico associado do Firestore.

Uso:
    python scripts/apagar_todos_chamados.py
    python scripts/apagar_todos_chamados.py --confirm   # pula confirmação (útil para automação)

Requer credentials.json na raiz do projeto (ou ADC em ambiente GCP).
"""

import firebase_admin
from firebase_admin import credentials, firestore
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

# Inicializa Firebase
try:
    firebase_admin.get_app()
except ValueError:
    cred_path = os.path.join(ROOT, 'credentials.json')
    if not os.path.exists(cred_path):
        print("Erro: credentials.json não encontrado na raiz do projeto.")
        sys.exit(1)
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()


def apagar_colecao(nome_colecao: str) -> int:
    """Apaga todos os documentos de uma coleção. Retorna a quantidade apagada."""
    ref = db.collection(nome_colecao)
    deletados = 0
    for doc in ref.stream():
        doc.reference.delete()
        deletados += 1
        print(f"  Deletado {nome_colecao}/{doc.id}")
    return deletados


def main():
    confirmar = '--confirm' in sys.argv or '-y' in sys.argv

    if not confirmar:
        print("=" * 60)
        print("ATENÇÃO: Este script apaga TODOS os chamados e todo o histórico.")
        print("Essa ação NÃO pode ser desfeita.")
        print("=" * 60)
        resp = input("Digite 'apagar' para confirmar: ").strip().lower()
        if resp != 'apagar':
            print("Operação cancelada.")
            sys.exit(0)

    print("\nApagando registros de histórico...")
    n_hist = apagar_colecao('historico')
    print(f"  Total histórico: {n_hist} registro(s) apagado(s).\n")

    print("Apagando chamados...")
    n_chamados = apagar_colecao('chamados')
    print(f"  Total chamados: {n_chamados} chamado(s) apagado(s).\n")

    print("=" * 60)
    print("Concluído.")
    print(f"  Histórico: {n_hist} | Chamados: {n_chamados}")
    print("=" * 60)


if __name__ == '__main__':
    main()
