#!/usr/bin/env python3
"""
Monitora o status do Cloud Build e Cloud Run deployment
Para usar: python check_deployment.py
"""

import subprocess
import json
import time
from datetime import datetime
from pathlib import Path

def run_cmd(cmd):
    """Executa comando e retorna saída"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout.strip(), result.returncode
    except Exception as e:
        return str(e), 1

def check_cloud_build():
    """Verifica status do último build"""
    print("\n" + "="*60)
    print("  VERIFICANDO CLOUD BUILD STATUS")
    print("="*60 + "\n")
    
    # Get latest build
    cmd = """gcloud builds list --limit=1 --format=json --project=sistema-de-chamados-dtx-aero"""
    output, code = run_cmd(cmd)
    
    if code != 0:
        print("❌ Erro ao conectar com gcloud")
        print("   Instale gcloud: https://cloud.google.com/sdk/docs/install")
        return None
    
    try:
        builds = json.loads(output)
        if not builds:
            print("⚠ Nenhum build encontrado")
            return None
        
        build = builds[0]
        build_id = build['id']
        status = build['status']
        create_time = build.get('createTime', 'N/A')
        finish_time = build.get('finishTime', 'N/A')
        
        # Status colors
        status_emoji = {
            'SUCCESS': '✅',
            'FAILURE': '❌',
            'TIMEOUT': '⏱️',
            'QUEUED': '⏳',
            'WORKING': '🔨',
            'CANCELLED': '🚫'
        }
        
        emoji = status_emoji.get(status, '❓')
        
        print(f"{emoji} Status: {status}")
        print(f"   Build ID: {build_id}")
        print(f"   Criado: {create_time}")
        print(f"   Finalizado: {finish_time}")
        
        if status == 'SUCCESS':
            print(f"\n✅ BUILD PASSOU! 🎉")
            print(f"   Próximo passo: Cloud Run deployment")
            return 'SUCCESS'
        elif status == 'FAILURE':
            print(f"\n❌ BUILD FALHOU")
            print(f"   Verifique logs em:")
            print(f"   https://console.cloud.google.com/cloud-build/builds/{build_id}")
            return 'FAILURE'
        elif status in ['QUEUED', 'WORKING']:
            print(f"\n⏳ BUILD EM ANDAMENTO")
            print(f"   Aguarde alguns minutos...")
            return 'WORKING'
        else:
            return status
            
    except json.JSONDecodeError:
        print("⚠ Erro ao parsear resposta do build")
        return None

def check_cloud_run():
    """Verifica status do Cloud Run"""
    print("\n" + "="*60)
    print("  VERIFICANDO CLOUD RUN STATUS")
    print("="*60 + "\n")
    
    cmd = """gcloud run services describe sistema-chamados-dtx --region us-central1 --format=json --project=sistema-de-chamados-dtx-aero"""
    output, code = run_cmd(cmd)
    
    if code != 0:
        print("⚠ Serviço Cloud Run ainda não deployado")
        print("   (Esperado se build acabou de passar)")
        return None
    
    try:
        service = json.loads(output)
        
        # Get URL
        url = None
        traffic = service.get('status', {}).get('traffic', [])
        if traffic and len(traffic) > 0:
            url = traffic[0].get('url')
        
        # Get status
        status = service.get('status', {}).get('conditions', [])
        ready = False
        for condition in status:
            if condition.get('type') == 'Ready':
                ready = condition.get('status') == 'True'
        
        emoji = '✅' if ready else '⏳'
        
        print(f"{emoji} Status: {'Pronto' if ready else 'Iniciando...'}")
        if url:
            print(f"   URL: {url}")
        print(f"   Region: us-central1")
        
        if ready and url:
            print(f"\n✅ SISTEMA NO AR! 🚀")
            print(f"   Acesse: {url}")
            return 'READY'
        else:
            print(f"\n⏳ Aguardando pronto...")
            return 'WARMING'
            
    except json.JSONDecodeError:
        print("⚠ Erro ao parsear resposta do Cloud Run")
        return None

def suggest_next_steps(build_status, run_status):
    """Sugere próximos passos"""
    print("\n" + "="*60)
    print("  PRÓXIMOS PASSOS")
    print("="*60 + "\n")
    
    if build_status == 'SUCCESS' and run_status == 'READY':
        print("✅ TUDO PRONTO!")
        print("   1. Acesse a URL do seu serviço Cloud Run")
        print("   2. Faça login")
        print("   3. Teste as features:")
        print("      - Dashboard")
        print("      - Exportar Avançado")
        print("      - Criar Chamado")
        print("      - Supervisores veem mesmo setor")
        return
    
    if build_status == 'SUCCESS' and run_status in [None, 'WARMING']:
        print("⏳ Aguarde Cloud Run deployment")
        print("   Verifique novamente em 2-3 minutos")
        print("   Acesse: https://console.cloud.google.com/run?project=sistema-de-chamados-dtx-aero")
        return
    
    if build_status == 'WORKING':
        print("⏳ Cloud Build ainda rodando")
        print("   Aguarde ~10 minutos")
        print("   Verifique novamente em alguns minutos")
        return
    
    if build_status == 'FAILURE':
        print("❌ Build falhou - tente:")
        print("   1. gcloud run deploy sistema-chamados-dtx --source . --region us-central1 --no-cache")
        print("   2. Ou verifique logs do build no Cloud Console")
        return
    
    print("❓ Status desconhecido - monitore manualmente em:")
    print("   Builds: https://console.cloud.google.com/cloud-build/builds?project=sistema-de-chamados-dtx-aero")
    print("   Cloud Run: https://console.cloud.google.com/run?project=sistema-de-chamados-dtx-aero")

def main():
    print("\n" + "🚀 "*30)
    print("MONITORADOR DE DEPLOYMENT - SISTEMA CHAMADOS DTX")
    print("🚀 "*30)
    print(f"Timestamp: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    
    # Check build
    build_status = check_cloud_build()
    
    # Check Cloud Run
    run_status = check_cloud_run()
    
    # Suggest next steps
    suggest_next_steps(build_status, run_status)
    
    print("\n" + "="*60)
    print("Monitore em tempo real:")
    print("  Builds: https://console.cloud.google.com/cloud-build/builds")
    print("  Cloud Run: https://console.cloud.google.com/run")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
