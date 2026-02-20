"""
Script para inicializar categorias padrão no Firestore.
Use este script para popular dados de exemplo se o banco estiver vazio.

Uso (a partir da raiz do projeto): python scripts/init_categorias.py
"""
import sys
import os

# Adiciona a raiz do projeto ao path (funciona em qualquer SO)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

from app.models_categorias import CategoriaSetor, CategoriaGate, CategoriaImpacto


def criar_setores_padrao():
    """Cria setores padrão se não existirem"""
    setores_padrao = [
        ("Manutenção", "Departamento de manutenção preventiva e corretiva"),
        ("Engenharia", "Departamento de engenharia e desenvolvimento"),
        ("Qualidade", "Departamento de controle de qualidade"),
        ("TI", "Departamento de tecnologia da informação"),
        ("Administrativo", "Departamento administrativo"),
    ]

    setores_existentes = CategoriaSetor.get_all()
    if len(setores_existentes) == 0:
        print("Criando setores padrão...")
        for nome_pt, descricao in setores_padrao:
            setor = CategoriaSetor(nome_pt=nome_pt, descricao_pt=descricao)
            setor.save()
            print(f"✅ Setor '{nome_pt}' criado")
    else:
        print(f"✅ {len(setores_existentes)} setor(es) já cadastrado(s)")


def criar_gates_padrao():
    """Cria gates padrão se não existirem"""
    gates_padrao = [
        ("Gate 1", "Validação inicial de requisitos", 1),
        ("Gate 2", "Análise de viabilidade técnica", 2),
        ("Gate 3", "Prototipagem e testes", 3),
        ("Gate 4", "Implementação em produção", 4),
    ]

    gates_existentes = CategoriaGate.get_all()
    if len(gates_existentes) == 0:
        print("\nCriando gates padrão...")
        for nome_pt, descricao, ordem in gates_padrao:
            gate = CategoriaGate(nome_pt=nome_pt, descricao_pt=descricao, ordem=ordem)
            gate.save()
            print(f"✅ Gate '{nome_pt}' criado com ordem {ordem}")
    else:
        print(f"\n✅ {len(gates_existentes)} gate(s) já cadastrado(s)")


def criar_impactos_padrao():
    """Cria impactos padrão se não existirem"""
    impactos_padrao = [
        ("Crítico", "Impacto crítico na operação - parada total"),
        ("Alto", "Impacto alto - grande degradação"),
        ("Médio", "Impacto médio - degradação parcial"),
        ("Baixo", "Impacto baixo - afeta funcionalidade secundária"),
    ]

    impactos_existentes = CategoriaImpacto.get_all()
    if len(impactos_existentes) == 0:
        print("\nCriando impactos padrão...")
        for nome_pt, descricao in impactos_padrao:
            impacto = CategoriaImpacto(nome_pt=nome_pt, descricao_pt=descricao)
            impacto.save()
            print(f"✅ Impacto '{nome_pt}' criado")
    else:
        print(f"\n✅ {len(impactos_existentes)} impacto(s) já cadastrado(s)")


if __name__ == '__main__':
    print("=" * 60)
    print("INICIALIZAÇÃO DE CATEGORIAS PADRÃO")
    print("=" * 60)

    criar_setores_padrao()
    criar_gates_padrao()
    criar_impactos_padrao()

    print("\n" + "=" * 60)
    print("✅ Inicialização concluída!")
    print("=" * 60)
