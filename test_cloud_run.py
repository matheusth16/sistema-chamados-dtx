#!/usr/bin/env python
"""
Teste do ambiente de produção similar ao Cloud Run.
Simula como gunicorn iniciaria a aplicação.
"""
import os
import sys
import logging

# Configurar variáveis de ambiente como no Cloud Run
os.environ['FLASK_ENV'] = 'production'
os.environ['PORT'] = '8080'
os.environ['PYTHONUNBUFFERED'] = '1'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

print("\n" + "="*60)
print("Teste de Ambiente Cloud Run")
print("="*60)
print(f"FLASK_ENV: {os.environ.get('FLASK_ENV')}")
print(f"PORT: {os.environ.get('PORT')}")
print(f"PYTHONUNBUFFERED: {os.environ.get('PYTHONUNBUFFERED')}")

try:
    print("\n[1/3] Importando aplicação...")
    from app import create_app
    print("✓ App importado com sucesso")
    
    print("\n[2/3] Criando app Flask...")
    app = create_app()
    print("✓ App criado com sucesso")
    
    print("\n[3/3] Verificando rotas...")
    routes_count = len(app.url_map._rules)
    print(f"✓ {routes_count} rotas registradas")
    
    print("\n" + "="*60)
    print("✓ TUDO FUNCIONANDO - Deploy deve estar OK!")
    print("="*60)
    
except Exception as e:
    print(f"\n✗ ERRO: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
