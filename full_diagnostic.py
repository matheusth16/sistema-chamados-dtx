#!/usr/bin/env python3
"""
Diagnostic completo para descobrir por que erro 51 persiste
"""

import subprocess
import sys
import os

def run(cmd, desc):
    print(f"\n{'='*60}")
    print(f"  {desc}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    return result.returncode == 0

print("\n🔍 DIAGNÓSTICO COMPLETO - SISTEMA CHAMADOS DTX\n")

# Test 1: Python version
run("python --version", "1. Python Version")

# Test 2: requirements.txt syntax
run("cat requirements.txt", "2. Requirements File Content")

# Test 3: Try installing requirements
run("pip install --dry-run -q -r requirements.txt 2>&1 | head -20", "3. Dry-run Install (primeiras linhas)")

# Test 4: Import all modules
print(f"\n{'='*60}")
print(f"  4. Test All Imports")
print(f"{'='*60}")

modules = [
    "flask",
    "firebase_admin",
    "pandas",
    "openpyxl",
    "gunicorn",
    "redis",
    "pytest",
]

for mod in modules:
    try:
        __import__(mod)
        print(f"✅ {mod}")
    except Exception as e:
        print(f"❌ {mod}: {e}")

# Test 5: App import
print(f"\n{'='*60}")
print(f"  5. Import Flask App")
print(f"{'='*60}")

try:
    from run import app
    print(f"✅ App importada")
    print(f"   Rotas: {len(app.url_map._rules)}")
except Exception as e:
    print(f"❌ Erro ao importar app: {e}")
    import traceback
    traceback.print_exc()

# Test 6: Check file permissions
print(f"\n{'='*60}")
print(f"  6. File Permissions")
print(f"{'='*60}")

files_to_check = [
    "requirements.txt",
    "run.py",
    "Dockerfile",
    "app/__init__.py",
]

for f in files_to_check:
    if os.path.exists(f):
        print(f"✅ {f}")
    else:
        print(f"❌ {f} NÃO ENCONTRADO")

# Test 7: Dockerfile analysis
print(f"\n{'='*60}")
print(f"  7. Dockerfile Analysis")
print(f"{'='*60}")

with open("Dockerfile", "r") as f:
    dockerfile = f.read()
    
if "python:3.11" in dockerfile:
    print("✅ Base image: python:3.11-slim")
else:
    print("⚠ Base image diferente de 3.11")

if "gunicorn" in dockerfile:
    print("✅ Gunicorn configurado")
else:
    print("❌ Gunicorn NÃO ENCONTRADO")

if "requirements.txt" in dockerfile:
    print("✅ requirements.txt copiado")
else:
    print("❌ requirements.txt NÃO COPIADO")

print("\n" + "="*60)
print("  RESUMO")
print("="*60)
print("""
Se tudo acima passou:
  → O problema é no Google Cloud Build (não no seu código)
  
Próximas ações:
  1. Veja os logs completos do build no Cloud Console
  2. Procure por "ERROR:" ou "Failed"
  3. Se precisar help, compartilhe a mensagem

Se algo falhou acima:
  1. Identifique qual teste falhou
  2. Corrija o arquivo correspondente
  3. Faça git add/commit/push
  4. Tente deploy novamente
""")

print("="*60 + "\n")
