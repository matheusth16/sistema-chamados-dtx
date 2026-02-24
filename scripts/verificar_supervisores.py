"""
Script para verificar quantos supervisores existem por área no Firestore
"""
import sys
import os

# Adicionar o diretório raiz ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import db
from app.models_usuario import Usuario

def verificar_supervisores():
    """Lista todos os supervisores e suas áreas"""
    print("=" * 80)
    print("VERIFICAÇÃO DE SUPERVISORES POR ÁREA")
    print("=" * 80)
    
    # Buscar todos os supervisores
    try:
        docs = db.collection('usuarios').where('perfil', '==', 'supervisor').stream()
        supervisores = [Usuario.from_dict(doc.to_dict(), doc.id) for doc in docs]
        
        print(f"\nTotal de supervisores cadastrados: {len(supervisores)}")
        print("\n" + "-" * 80)
        
        # Agrupar por área
        areas_dict = {}
        for sup in supervisores:
            print(f"\nSupervisor: {sup.nome}")
            print(f"  Email: {sup.email}")
            print(f"  ID: {sup.id}")
            print(f"  Áreas: {sup.areas if hasattr(sup, 'areas') else 'NÃO DEFINIDO'}")
            
            # Adicionar ao dicionário de áreas
            if hasattr(sup, 'areas') and sup.areas:
                for area in sup.areas:
                    if area not in areas_dict:
                        areas_dict[area] = []
                    areas_dict[area].append(sup.nome)
        
        # Resumo por área
        print("\n" + "=" * 80)
        print("RESUMO POR ÁREA")
        print("=" * 80)
        
        for area, sups in sorted(areas_dict.items()):
            print(f"\n- {area}: {len(sups)} supervisor(es)")
            for i, nome in enumerate(sups, 1):
                print(f"   {i}. {nome}")
        
        # Buscar também admins
        print("\n" + "=" * 80)
        print("VERIFICANDO ADMINS")
        print("=" * 80)
        
        docs_admin = db.collection('usuarios').where('perfil', '==', 'admin').stream()
        admins = [Usuario.from_dict(doc.to_dict(), doc.id) for doc in docs_admin]
        
        print(f"\nTotal de admins cadastrados: {len(admins)}")
        
        for admin in admins:
            print(f"\nAdmin: {admin.nome}")
            print(f"  Email: {admin.email}")
            print(f"  ID: {admin.id}")
            print(f"  Áreas: {admin.areas if hasattr(admin, 'areas') else 'NÃO DEFINIDO'}")
        
        # Testar a função get_supervisores_por_area para cada área
        print("\n" + "=" * 80)
        print("TESTANDO get_supervisores_por_area()")
        print("=" * 80)
        
        for area in sorted(areas_dict.keys()):
            print(f"\n>> Testando area '{area}'...")
            resultado = Usuario.get_supervisores_por_area(area)
            print(f"   Resultado recebido: {len(resultado)} supervisor(es) + admin(s)")
            print(f"   Detalhes do resultado:")
            for i, sup in enumerate(resultado, 1):
                print(f"      {i}. {sup.nome} ({sup.perfil}) - ID: {sup.id}")
                print(f"         Áreas: {sup.areas if hasattr(sup, 'areas') else 'N/A'}")
        
    except Exception as e:
        print(f"\nERRO: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    verificar_supervisores()
