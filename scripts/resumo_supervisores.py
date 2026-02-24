"""
Script resumido para mostrar supervisores por setor
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import db
from app.models_usuario import Usuario

def resumo():
    print("=" * 80)
    print("SUPERVISORES CADASTRADOS POR SETOR")
    print("=" * 80)
    
    # Buscar todos os supervisores
    docs = db.collection('usuarios').where('perfil', '==', 'supervisor').stream()
    supervisores = [Usuario.from_dict(doc.to_dict(), doc.id) for doc in docs]
    
    # Agrupar por área
    areas_dict = {}
    for sup in supervisores:
        if hasattr(sup, 'areas') and sup.areas:
            for area in sup.areas:
                if area not in areas_dict:
                    areas_dict[area] = []
                areas_dict[area].append(sup.nome)
    
    # Mostrar resumo
    if not areas_dict:
        print("\nNENHUM SUPERVISOR CADASTRADO!")
        return
    
    for area in sorted(areas_dict.keys()):
        sups = areas_dict[area]
        print(f"\n{area}: {len(sups)} supervisor(es)")
        for i, nome in enumerate(sups, 1):
            print(f"   {i}. {nome}")
    
    print("\n" + "=" * 80)
    print("TESTANDO A API get_supervisores_por_area()")
    print("=" * 80)
    
    for area in sorted(areas_dict.keys()):
        resultado = Usuario.get_supervisores_por_area(area)
        print(f"\n{area}: API retorna {len(resultado)} supervisor(es)")
        if len(resultado) != len(areas_dict[area]):
            print(f"   ERRO! Esperado {len(areas_dict[area])}, retornou {len(resultado)}")
        else:
            print(f"   OK! Todos os supervisores retornados corretamente")

if __name__ == '__main__':
    resumo()
