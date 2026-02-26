"""
Script para atualizar Firebase com as categorias exatas do formulário
"""
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from datetime import datetime
import os

# Garante que credentials.json seja encontrado na raiz do projeto
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

# Inicializa Firebase
try:
    firebase_admin.get_app()
except ValueError:
    cred = credentials.Certificate(os.path.join(ROOT, 'credentials.json'))
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Limpa as collections antigas
print("Limpando categorias antigas...")
for doc in db.collection('categorias_setores').stream():
    db.collection('categorias_setores').document(doc.id).delete()
    print(f"  Deletado setor: {doc.id}")

for doc in db.collection('categorias_impactos').stream():
    db.collection('categorias_impactos').document(doc.id).delete()
    print(f"  Deletado impacto: {doc.id}")

print("\nCriando novos setores...")

# Setores EXATOS do formulário
setores_dados = [
    {
        'nome_pt': 'Manutenção',
        'nome_en': 'Maintenance',
        'nome_es': 'Mantenimiento',
        'ativo': True,
        'criado_em': datetime.now()
    },
    {
        'nome_pt': 'Engenharia',
        'nome_en': 'Engineering',
        'nome_es': 'Ingeniería',
        'ativo': True,
        'criado_em': datetime.now()
    },
    {
        'nome_pt': 'Qualidade',
        'nome_en': 'Quality',
        'nome_es': 'Calidad',
        'ativo': True,
        'criado_em': datetime.now()
    },
    {
        'nome_pt': 'Comercial',
        'nome_en': 'Commercial',
        'nome_es': 'Comercial',
        'ativo': True,
        'criado_em': datetime.now()
    },
    {
        'nome_pt': 'Planejamento',
        'nome_en': 'Planning',
        'nome_es': 'Planificación',
        'ativo': True,
        'criado_em': datetime.now()
    },
    {
        'nome_pt': 'Material Indireto / Compras',
        'nome_en': 'Indirect Material / Procurement',
        'nome_es': 'Material Indirecto / Compras',
        'ativo': True,
        'criado_em': datetime.now()
    }
]

for setor in setores_dados:
    doc_ref = db.collection('categorias_setores').add(setor)
    print(f"[OK] Setor '{setor['nome_pt']}' criado")

print("\nCriando novos impactos...")

# Impactos EXATOS do formulário
impactos_dados = [
    {
        'nome_pt': 'Prazo / Cliente',
        'nome_en': 'Deadline / Customer',
        'nome_es': 'Plazo / Cliente',
        'ativo': True,
        'criado_em': datetime.now()
    },
    {
        'nome_pt': 'Qualidade',
        'nome_en': 'Quality',
        'nome_es': 'Calidad',
        'ativo': True,
        'criado_em': datetime.now()
    },
    {
        'nome_pt': 'Segurança',
        'nome_en': 'Safety',
        'nome_es': 'Seguridad',
        'ativo': True,
        'criado_em': datetime.now()
    }
]

for impacto in impactos_dados:
    doc_ref = db.collection('categorias_impactos').add(impacto)
    print(f"[OK] Impacto '{impacto['nome_pt']}' criado")

print("\nFirebase atualizado com sucesso!")
print("Total: 6 setores + 3 impactos")
