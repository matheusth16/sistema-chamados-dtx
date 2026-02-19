#!/usr/bin/env python
"""
Diagnóstico completo - Simula o processo de build do Google Cloud Buildpacks.
Identifica exatamente onde o erro está ocorrendo.
"""
import os
import sys
import subprocess
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
os.chdir(PROJECT_ROOT)

print("\n" + "="*70)
print("DIAGNÓSTICO DO BUILD - Google Cloud Buildpacks")
print("="*70)

# ===========================================================================
# TESTE 1: Verificar Python
# ===========================================================================
print("\n[TEST 1/6] Verificando Python...")
try:
    result = subprocess.run([sys.executable, '--version'], capture_output=True, text=True)
    print(f"  ✓ {result.stdout.strip()}")
except Exception as e:
    print(f"  ✗ ERRO: {e}")
    sys.exit(1)

# ===========================================================================
# TESTE 2: Instalar/Verificar requirements
# ===========================================================================
print("\n[TEST 2/6] Instalando/verificando dependencies...")
try:
    # Ler requirements
    with open('requirements.txt', 'r') as f:
        reqs = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    print(f"  - {len(reqs)} dependências para verificar")
    
    # Tentar instalar silenciosamente
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '-q'] + reqs,
        capture_output=True,
        text=True,
        timeout=120
    )
    
    if result.returncode != 0:
        print(f"  ✗ ERRO ao instalar dependências:")
        print(result.stderr)
        sys.exit(1)
    else:
        print(f"  ✓ Todas as dependências instaladas com sucesso")
        
except Exception as e:
    print(f"  ✗ ERRO: {e}")
    sys.exit(1)

# ===========================================================================
# TESTE 3: Verificar importações críticas
# ===========================================================================
print("\n[TEST 3/6] Testando importações críticas...")
critical_modules = [
    'flask',
    'firebase_admin',
    'pandas',
    'openpyxl',
]

for module in critical_modules:
    try:
        __import__(module)
        print(f"  ✓ {module}")
    except ImportError as e:
        print(f"  ✗ {module}: {e}")
        sys.exit(1)

# ===========================================================================
# TESTE 4: Importar aplicação
# ===========================================================================
print("\n[TEST 4/6] Importando e criando aplicação Flask...")
try:
    os.environ['FLASK_ENV'] = 'production'
    os.environ['PORT'] = '8080'
    
    from app import create_app
    app = create_app()
    
    routes = len(app.url_map._rules)
    print(f"  ✓ Aplicação criada com sucesso ({routes} rotas)")
    
except Exception as e:
    print(f"  ✗ ERRO ao criar app: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ===========================================================================
# TESTE 5: Verificar arquivo WSGI (para gunicorn)
# ===========================================================================
print("\n[TEST 5/6] Verificando WSGI entry point...")
try:
    # O Dockerfile usa: gunicorn --bind 0.0.0.0:${PORT} run:app
    # Isso significa que precisa haver um app exportado em run.py
    
    import run
    if hasattr(run, 'app'):
        print(f"  ✓ run:app está disponível para gunicorn")
    else:
        print(f"  ✗ run:app NÃO encontrado")
        sys.exit(1)
        
except Exception as e:
    print(f"  ✗ ERRO: {e}")
    sys.exit(1)

# ===========================================================================
# TESTE 6: Verificar credenciais Firebase
# ===========================================================================
print("\n[TEST 6/6] Verificando credenciais Firebase...")
try:
    # No Cloud Run, as credenciais vêm automaticamente
    # Em local, tenta usar credentials.json
    
    cred_path = PROJECT_ROOT / 'credentials.json'
    
    if cred_path.exists():
        print(f"  ✓ credentials.json encontrado (local)")
    else:
        print(f"  ⓘ credentials.json NÃO encontrado")
        print(f"    (Isso é OK - Cloud Run usa Application Default Credentials)")
    
    # Testar se firebase_admin está importável
    import firebase_admin
    print(f"  ✓ firebase_admin importável")
    
except Exception as e:
    print(f"  ✗ ERRO: {e}")
    sys.exit(1)

# ===========================================================================
# RESUMO FINAL
# ===========================================================================
print("\n" + "="*70)
print("✓ TODOS OS TESTES PASSARAM - BUILD DEVE FUNCIONAR!")
print("="*70)
print("\nPossíveis causas do erro no Cloud Build:")
print("  1. Timeout (aumentar tempo do build)")
print("  2. Memória insuficiente")
print("  3. Quotas do projeto Google Cloud")
print("  4. Erro na configuração do serviço")
print("\nPróximos passos:")
print("  1. Verifique os logs completos do build no Cloud Console")
print("  2. Tente fazer deploy novamente")
print("="*70)
