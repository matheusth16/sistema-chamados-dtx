#!/usr/bin/env python3
"""
Script para migrar usuários existentes adicionando campos de controle de senha.

Adiciona os campos:
- must_change_password: False (assumido que já trocaram a senha)
- password_changed_at: None

Uso: python scripts/migrar_campo_senha.py (a partir da raiz do projeto)
"""

import os
import sys

# Adiciona a raiz do projeto ao path (script está em scripts/)
_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _raiz)

from app.database import db  # noqa: E402


def migrar_usuarios():
    """Adiciona campos de controle de senha a todos os usuários existentes"""
    print("\n" + "=" * 70)
    print("  🔄 MIGRAÇÃO - Adicionar campos de controle de senha")
    print("=" * 70)

    try:
        # Buscar todos os usuários
        usuarios_ref = db.collection("usuarios")
        docs = usuarios_ref.stream()

        usuarios_atualizados = 0
        usuarios_ja_com_campos = 0
        erros = 0

        print("\n📋 Processando usuários...\n")

        for doc in docs:
            try:
                data = doc.to_dict()
                usuario_id = doc.id
                email = data.get("email", "email_desconhecido")

                # Verificar se já tem os campos
                if "must_change_password" in data and "password_changed_at" in data:
                    print(f"   ⏭️  {email} - Já possui os campos, pulando...")
                    usuarios_ja_com_campos += 1
                    continue

                # Preparar dados de atualização
                update_data = {}

                if "must_change_password" not in data:
                    # Usuários existentes presumivelmente já trocaram a senha
                    update_data["must_change_password"] = False

                if "password_changed_at" not in data:
                    update_data["password_changed_at"] = None

                # Atualizar documento
                if update_data:
                    usuarios_ref.document(usuario_id).update(update_data)
                    print(f"   ✅ {email} - Campos adicionados com sucesso")
                    usuarios_atualizados += 1

            except Exception as e:
                print(f"   ❌ Erro ao processar {email}: {str(e)}")
                erros += 1

        # Resumo
        print("\n" + "=" * 70)
        print("  📊 RESUMO DA MIGRAÇÃO")
        print("=" * 70)
        print(f"✅ Usuários atualizados:      {usuarios_atualizados}")
        print(f"⏭️  Usuários já com campos:    {usuarios_ja_com_campos}")
        print(f"❌ Erros:                     {erros}")
        print(
            f"📊 Total processado:          {usuarios_atualizados + usuarios_ja_com_campos + erros}"
        )
        print("=" * 70)

        if erros == 0:
            print("\n✅ Migração concluída com sucesso!\n")
            return True
        else:
            print(f"\n⚠️  Migração concluída com {erros} erro(s).\n")
            return False

    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO durante a migração: {str(e)}\n")
        return False


def verificar_migracao():
    """Verifica o status da migração"""
    print("\n" + "=" * 70)
    print("  🔍 VERIFICAÇÃO - Status dos campos de senha")
    print("=" * 70)

    try:
        usuarios_ref = db.collection("usuarios")
        docs = usuarios_ref.stream()

        com_campos = 0
        sem_campos = 0

        print("\n📋 Status dos usuários:\n")

        for doc in docs:
            data = doc.to_dict()
            email = data.get("email", "email_desconhecido")
            perfil = data.get("perfil", "não definido")

            tem_must_change = "must_change_password" in data
            tem_password_changed_at = "password_changed_at" in data

            if tem_must_change and tem_password_changed_at:
                must_change_value = data.get("must_change_password")
                status_icon = "🔒" if must_change_value else "✅"
                print(
                    f"   {status_icon} {email:<30} | {perfil:<12} | must_change: {must_change_value}"
                )
                com_campos += 1
            else:
                print(f"   ⚠️  {email:<30} | {perfil:<12} | FALTAM CAMPOS")
                sem_campos += 1

        print("\n" + "=" * 70)
        print(f"✅ Com campos:     {com_campos}")
        print(f"⚠️  Sem campos:     {sem_campos}")
        print("=" * 70 + "\n")

        return sem_campos == 0

    except Exception as e:
        print(f"\n❌ ERRO ao verificar: {str(e)}\n")
        return False


def menu_principal():
    """Menu principal do script"""
    while True:
        print("\n" + "=" * 70)
        print("  🔐 MIGRAÇÃO DE CAMPOS DE SENHA")
        print("=" * 70)
        print("\n  Opções:")
        print("    1️⃣  Executar migração")
        print("    2️⃣  Verificar status da migração")
        print("    3️⃣  Sair")
        print("\n" + "=" * 70)

        opcao = input("\n  Escolha uma opção (1-3): ").strip()

        if opcao == "1":
            confirmacao = input("\n  ⚠️  Deseja executar a migração? (S/N): ").strip().upper()
            if confirmacao == "S":
                migrar_usuarios()
            else:
                print("\n  ❌ Operação cancelada.\n")

        elif opcao == "2":
            verificar_migracao()

        elif opcao == "3":
            print("\n  👋 Até logo!\n")
            break

        else:
            print("\n  ❌ Opção inválida!\n")


if __name__ == "__main__":
    try:
        menu_principal()
    except KeyboardInterrupt:
        print("\n\n  ⚠️  Operação interrompida pelo usuário.\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ ERRO FATAL: {str(e)}\n")
        sys.exit(1)
