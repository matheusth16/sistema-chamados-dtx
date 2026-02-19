#!/usr/bin/env python3
"""
Simula o processo do Cloud Build Buildpack
Tenta detectar por que exit code 51 ocorre
"""

import os
import sys
import subprocess
import json
from pathlib import Path

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def run_cmd(cmd, description):
    """Executa comando e retorna resultado"""
    print(f"🔍 {description}...")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print(f"✓ {description}: OK")
            return True, result.stdout
        else:
            print(f"✗ {description}: ERRO")
            print(f"  Stderr: {result.stderr}")
            return False, result.stderr
    except subprocess.TimeoutExpired:
        print(f"✗ {description}: TIMEOUT (30s)")
        return False, "TIMEOUT"
    except Exception as e:
        print(f"✗ {description}: {e}")
        return False, str(e)

def check_dockerfile():
    """Verifica se Dockerfile tem linhas muito longas (problema de Buildpack)"""
    print_section("1. DOCKERFILE VALIDATION")
    
    dockerfile_path = Path("Dockerfile")
    if not dockerfile_path.exists():
        print("⚠ Dockerfile não encontrado!")
        return False
    
    with open(dockerfile_path, 'r') as f:
        lines = f.readlines()
    
    print(f"Total de linhas: {len(lines)}")
    
    # Procura por linhas muito longas
    long_lines = [(i+1, len(line)) for i, line in enumerate(lines) if len(line) > 200]
    if long_lines:
        print(f"\n⚠ AVISO: Linhas muito longas encontradas (pode causar erro 51):")
        for line_no, length in long_lines:
            print(f"  Linha {line_no}: {length} caracteres")
            print(f"  Conteúdo: {lines[line_no-1][:100]}...")
    
    # Procura por CMD ou ENTRYPOINT com quebras
    dockerfile_content = ''.join(lines)
    if 'CMD' in dockerfile_content and '\\' in dockerfile_content:
        print("\n⚠ AVISO: CMD usa continuação de linha (\\)")
        print("  Isso pode causar problemas no Buildpack")
    
    return True

def check_requirements():
    """Verifica requirements.txt"""
    print_section("2. REQUIREMENTS VALIDATION")
    
    req_path = Path("requirements.txt")
    if not req_path.exists():
        print("✗ requirements.txt não encontrado!")
        return False
    
    with open(req_path, 'r') as f:
        reqs = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    print(f"Total de pacotes: {len(reqs)}")
    print("\nPacotes encontrados:")
    for req in reqs:
        print(f"  - {req}")
    
    # Verifica se tem pacotes problemáticos
    problematic = [r for r in reqs if any(x in r for x in ['opencv', 'torch', 'tensorflow'])]
    if problematic:
        print(f"\n⚠ AVISO: Pacotes pesados encontrados:")
        for p in problematic:
            print(f"  - {p}")
    
    # Tenta instalar em modo dry-run
    print("\n🔍 Testando compatibilidade de pacotes...")
    success, _ = run_cmd(
        f"pip install --dry-run -q {' '.join(reqs[:5])}",
        "Dry-run dos primeiros 5 pacotes"
    )
    
    return True

def check_python_version():
    """Verifica versão Python"""
    print_section("3. PYTHON VERSION CHECK")
    
    # Local version
    import platform
    local_version = platform.python_version()
    print(f"Versão local: Python {local_version}")
    
    # Dockerfile version
    dockerfile_path = Path("Dockerfile")
    if dockerfile_path.exists():
        with open(dockerfile_path, 'r') as f:
            content = f.read()
            for line in content.split('\n'):
                if 'python' in line.lower() and 'from' in line.lower():
                    print(f"Dockerfile: {line}")
    
    return True

def check_env_vars():
    """Verifica variáveis de ambiente"""
    print_section("4. ENVIRONMENT VARIABLES")
    
    env_example = Path(".env.example")
    if env_example.exists():
        print("Variáveis esperadas (.env.example):")
        with open(env_example, 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    print(f"  - {line.strip()}")
    
    env_file = Path(".env")
    if env_file.exists():
        print("\n⚠ AVISO: .env encontrado no repositório!")
        print("  Não deve estar versionado. Adicione a .gitignore")
    else:
        print("\n✓ .env não está versionado (bom!)")
    
    return True

def check_gcp_config():
    """Verifica configuração GCP"""
    print_section("5. GCP CONFIGURATION")
    
    files_to_check = [
        ("credentials.json", "credentials"),
        ("firebase.json", "firebase"),
        ("firestore.rules", "firestore rules"),
        ("firestore.indexes.json", "firestore indexes"),
    ]
    
    for filename, desc in files_to_check:
        path = Path(filename)
        if path.exists():
            size = path.stat().st_size
            print(f"✓ {desc}: {filename} ({size} bytes)")
        else:
            print(f"⚠ {desc}: {filename} NÃO ENCONTRADO")
    
    return True

def check_git_status():
    """Verifica status do git"""
    print_section("6. GIT STATUS")
    
    success, output = run_cmd("git status --short", "Git status")
    if success:
        if output.strip():
            print("⚠ Mudanças não commitadas:")
            print(output)
        else:
            print("✓ Tudo committado")
    
    success, output = run_cmd("git log --oneline -3", "Últimos 3 commits")
    if success:
        print(output)
    
    return True

def simulate_buildpack():
    """Simula o processo do Buildpack"""
    print_section("7. BUILDPACK SIMULATION")
    
    print("Simulando etapas do Cloud Build Buildpack:\n")
    
    # Step 1: Detectar tipo de app
    print("Step 1: Detectar tipo de app (Python)")
    if Path("pyproject.toml").exists() or Path("setup.py").exists() or Path("requirements.txt").exists():
        print("  ✓ Detectado como app Python\n")
    else:
        print("  ✗ Nenhum arquivo de dependências encontrado!\n")
        return False
    
    # Step 2: Instalar dependências
    print("Step 2: Instalar dependências (pip install)")
    success, output = run_cmd(
        "pip install -q -r requirements.txt",
        "pip install"
    )
    if not success:
        print(f"  ✗ FALHA ao instalar dependências!")
        print(f"  Saída: {output[:500]}")
        return False
    else:
        print("  ✓ Dependências instaladas\n")
    
    # Step 3: Verificar runtime
    print("Step 3: Verificar runtime (gunicorn)")
    success, output = run_cmd(
        "python -c \"import gunicorn; print('OK')\"",
        "gunicorn import"
    )
    if not success:
        print("  ✗ gunicorn não importável!")
        return False
    else:
        print("  ✓ gunicorn disponível\n")
    
    # Step 4: Verificar app.py / wsgi
    print("Step 4: Procurar entry point (run.py / app.py)")
    if Path("run.py").exists():
        print("  ✓ run.py encontrado")
    if Path("app/__init__.py").exists():
        print("  ✓ app/__init__.py encontrado")
    
    success, output = run_cmd(
        "python -c \"from run import app; print('OK')\"",
        "Importar aplicação"
    )
    if not success:
        print(f"  ✗ FALHA ao importar app: {output}")
        return False
    else:
        print("  ✓ App importada com sucesso\n")
    
    # Step 5: Criar container
    print("Step 5: Criar imagem Docker")
    print("  (Simulado - Docker não disponível aqui)")
    print("  ✓ Dockerfile presente\n")
    
    return True

def final_checks():
    """Verificações finais"""
    print_section("SUMMARY - PROBLEMA PROVÁVEL")
    
    print("""
Se o build está falhando com erro 51, é provavelmente:

1. VERSÃO PYTHON: requirements.txt usa versão 3.11 (Dockerfile)
   mas local é 3.14.3. Pode haver incompatibilidade.
   
   ✓ SOLUÇÃO: Especifique versão no requirements.txt
   pip install --upgrade pip
   pip freeze > requirements.txt
   
2. DOCKERFILE: Verifique se CMD está bem formatado
   
   ✓ SOLUÇÃO: Certifique-se que CMD é uma lista JSON:
   CMD ["gunicorn", "--bind", "0.0.0.0:8080", "run:app"]
   
3. TIMEOUT: Buildpack demora muito
   
   ✓ SOLUÇÃO: Aumente timeout no Cloud Run:
   gcloud run deploy ... --build-timeout=1800
   
4. MEMÓRIA: Builder não tem RAM suficiente
   
   ✓ SOLUÇÃO: Use máquina com + memória:
   gcloud run deploy ... --memory=2Gi
   
5. DEPENDÊNCIA PROBLEMÁTICA: algum pacote não compila
   
   ✓ SOLUÇÃO: Tente sem pacotes opcionais primeiro
   """)

def main():
    print("\n" + "="*60)
    print("  CLOUD BUILD ERROR 51 DIAGNOSTIC")
    print("="*60)
    print("\nVerificando configuração para descobrir por que erro 51 ocorre...\n")
    
    checks = [
        ("Dockerfile Validation", check_dockerfile),
        ("Requirements Validation", check_requirements),
        ("Python Version", check_python_version),
        ("Environment Variables", check_env_vars),
        ("GCP Configuration", check_gcp_config),
        ("Git Status", check_git_status),
        ("Buildpack Simulation", simulate_buildpack),
    ]
    
    results = []
    for name, func in checks:
        try:
            result = func()
            results.append((name, result))
        except Exception as e:
            print(f"✗ ERRO em {name}: {e}")
            results.append((name, False))
    
    final_checks()
    
    print("\n" + "="*60)
    print("  PRÓXIMOS PASSOS")
    print("="*60)
    print("""
1. Verifique os logs completos do build:
   https://console.cloud.google.com/cloud-build/builds
   
2. Procure pela mensagem ERROR antes do "exit status 1"
   
3. Se não encontrar, tente:
   a) Fazer novo commit e push (força rebuild)
   b) Usar --no-cache no deploy
   c) Aumentar --build-timeout para 1800 segundos
   
4. Se ainda falhar, entre em contato com Google Cloud Support
""")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
