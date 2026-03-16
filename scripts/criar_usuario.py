#!/usr/bin/env python3
"""
Script para criar usuários no sistema de chamados
Uso: python scripts/criar_usuario.py (a partir da raiz do projeto)
"""

import os
import sys
from getpass import getpass

# Adiciona a raiz do projeto ao path (script está em scripts/)
_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _raiz)

from app.database import db  # noqa: E402
from app.models_usuario import Usuario  # noqa: E402


def limpar_tela():
    """Limpa a tela do terminal"""
    os.system("cls" if os.name == "nt" else "clear")


def exibir_menu():
    """Exibe o menu principal"""
    print("\n" + "=" * 60)
    print("  🔐 CRIAR NOVO USUÁRIO - Sistema de Chamados DTX Aerospace")
    print("=" * 60)


def criar_usuario_interativo():
    """Cria um usuário através de perguntas interativas"""
    exibir_menu()

    # 1. Email
    print("\n📧 Email:")
    email = input("Digite o email (ex: joao@dtx.com): ").strip().lower()

    if not email or "@" not in email:
        print("❌ Email inválido!")
        return False

    # Verifica se já existe
    usuario_existente = Usuario.get_by_email(email)
    if usuario_existente:
        print(f"❌ Usuário com email '{email}' já existe!")
        return False

    # 2. Nome
    print("\n👤 Nome Completo:")
    nome = input("Digite o nome: ").strip()

    if not nome or len(nome) < 3:
        print("❌ Nome inválido (mínimo 3 caracteres)!")
        return False

    # 3. Perfil
    print("\n👥 Perfil:")
    print("  1️⃣  Solicitante (cria chamados)")
    print("  2️⃣  Supervisor (gerencia uma área)")
    print("  3️⃣  Admin (acesso total)")

    opcao_perfil = input("\nEscolha (1/2/3): ").strip()

    perfis = {"1": "solicitante", "2": "supervisor", "3": "admin"}

    if opcao_perfil not in perfis:
        print("❌ Opção inválida!")
        return False

    perfil = perfis[opcao_perfil]

    # 4. Área (se supervisor ou admin)
    area = None
    if perfil in ["supervisor", "admin"]:
        print("\n🏢 Área/Departamento:")
        print("  1️⃣  Manutencao")
        print("  2️⃣  Engenharia")
        print("  3️⃣  Qualidade")
        print("  4️⃣  Comercial")
        print("  5️⃣  Planejamento")
        print("  6️⃣  Material")
        print("  7️⃣  Outro")

        opcao_area = input("\nEscolha (1-7): ").strip()

        areas_map = {
            "1": "Manutencao",
            "2": "Engenharia",
            "3": "Qualidade",
            "4": "Comercial",
            "5": "Planejamento",
            "6": "Material",
            "7": None,
        }

        if opcao_area not in areas_map:
            print("❌ Opção inválida!")
            return False

        if opcao_area == "7":
            area = input("Digite a área customizada: ").strip()
            if not area:
                print("❌ Área não pode estar vazia!")
                return False
        else:
            area = areas_map[opcao_area]

    # 5. Senha
    print("\n🔑 Senha:")
    while True:
        senha = getpass("Digite a senha (mínimo 6 caracteres): ")

        if len(senha) < 6:
            print("❌ Senha deve ter mínimo 6 caracteres!")
            continue

        confirmacao = getpass("Confirme a senha: ")

        if senha == confirmacao:
            break
        else:
            print("❌ Senhas não conferem!")

    # 6. Resumo
    print("\n" + "=" * 60)
    print("  📋 RESUMO DO NOVO USUÁRIO")
    print("=" * 60)
    print(f"📧 Email:    {email}")
    print(f"👤 Nome:     {nome}")
    print(f"👥 Perfil:   {perfil.upper()}")
    if area:
        print(f"🏢 Área:     {area}")
    print("=" * 60)

    # 7. Confirmação
    confirmacao = input("\n✅ Criar usuário? (S/N): ").strip().upper()

    if confirmacao != "S":
        print("❌ Operação cancelada!")
        return False

    # 8. Criar usuário
    try:
        usuario = Usuario(
            id=f"user_{email.split('@')[0]}_{hash(email) % 10000}",
            email=email,
            nome=nome,
            perfil=perfil,
            areas=[area] if area else [],
            must_change_password=(perfil in ["solicitante", "supervisor"]),
            password_changed_at=None,
        )
        usuario.set_password(senha)
        usuario.save()

        print("\n✅ SUCESSO!")
        print(f"   Usuário '{nome}' ({email}) criado com sucesso!")
        print(f"   ID do usuário: {usuario.id}")
        if perfil in ["solicitante", "supervisor"]:
            print("   ⚠️  Deverá trocar a senha no primeiro acesso")
        return True

    except Exception as e:
        print(f"\n❌ ERRO ao criar usuário: {str(e)}")
        return False


def criar_usuario_rapido():
    """Modo rápido para criar usuário com comando de uma linha"""
    exibir_menu()

    print("\n💡 Modo Rápido - Preencha os dados:")
    print("   (Deixe em branco para usar valor padrão)\n")

    email = input("Email [padrão: teste@dtx.com]: ").strip().lower() or "teste@dtx.com"
    nome = input("Nome [padrão: Usuário Teste]: ").strip() or "Usuário Teste"
    perfil_input = (
        input("Perfil - solicitante/supervisor/admin [padrão: solicitante]: ").strip().lower()
        or "solicitante"
    )
    area = input("Área (deixe em branco se solicitante) [padrão: Manutencao]: ").strip() or None

    if perfil_input not in ["solicitante", "supervisor", "admin"]:
        print("❌ Perfil inválido!")
        return False

    perfil = perfil_input

    # Se não definiu área e é gestor, usa padrão
    if not area and perfil != "solicitante":
        area = "Manutencao"

    try:
        usuario = Usuario(
            id=f"user_{email.split('@')[0]}_{hash(email) % 10000}",
            email=email,
            nome=nome,
            perfil=perfil,
            areas=[area] if area else [],
            must_change_password=(perfil in ["solicitante", "supervisor"]),
            password_changed_at=None,
        )
        usuario.set_password("123456")
        usuario.save()

        print("\n✅ SUCESSO!")
        print(f"   Email: {email}")
        print("   Senha: 123456")
        print(f"   Tipo: {perfil}")
        if area:
            print(f"   Área: {area}")
        if perfil in ["solicitante", "supervisor"]:
            print("   ⚠️  Deverá trocar a senha no primeiro acesso")
        return True

    except Exception as e:
        print(f"\n❌ ERRO: {str(e)}")
        return False


def listar_usuarios():
    """Lista todos os usuários"""
    exibir_menu()

    try:
        docs = db.collection("usuarios").stream()
        usuarios = []

        for doc in docs:
            data = doc.to_dict()
            usuarios.append(
                {
                    "id": doc.id,
                    "email": data.get("email"),
                    "nome": data.get("nome"),
                    "perfil": data.get("perfil"),
                    "area": data.get("area"),
                }
            )

        if not usuarios:
            print("\n❌ Nenhum usuário cadastrado!")
            return

        print(f"\n📋 Total de usuários: {len(usuarios)}\n")
        print("-" * 100)
        print(f"{'ID':<20} {'Email':<25} {'Nome':<20} {'Perfil':<12} {'Área':<15}")
        print("-" * 100)

        for u in usuarios:
            area_str = u["area"] or "-"
            print(
                f"{u['id']:<20} {u['email']:<25} {u['nome']:<20} {u['perfil']:<12} {area_str:<15}"
            )

        print("-" * 100)

    except Exception as e:
        print(f"\n❌ ERRO ao listar usuários: {str(e)}")


def menu_principal():
    """Menu principal"""
    while True:
        limpar_tela()

        print("\n" + "=" * 60)
        print("  🔐 GERENCIAR USUÁRIOS - Sistema de Chamados")
        print("=" * 60)
        print("\n  1️⃣  Criar novo usuário (Modo Interativo)")
        print("  2️⃣  Criar novo usuário (Modo Rápido)")
        print("  3️⃣  Listar usuários")
        print("  4️⃣  Sair")
        print("\n" + "=" * 60)

        opcao = input("\nEscolha uma opção (1/2/3/4): ").strip()

        if opcao == "1":
            criar_usuario_interativo()
            input("\n[Pressione ENTER para continuar]")
        elif opcao == "2":
            criar_usuario_rapido()
            input("\n[Pressione ENTER para continuar]")
        elif opcao == "3":
            listar_usuarios()
            input("\n[Pressione ENTER para continuar]")
        elif opcao == "4":
            print("\n👋 Até logo!")
            break
        else:
            print("\n❌ Opção inválida!")
            input("[Pressione ENTER para continuar]")


if __name__ == "__main__":
    try:
        menu_principal()
    except KeyboardInterrupt:
        print("\n\n👋 Operação cancelada!")
    except Exception as e:
        print(f"\n❌ ERRO: {str(e)}")
        import traceback

        traceback.print_exc()
