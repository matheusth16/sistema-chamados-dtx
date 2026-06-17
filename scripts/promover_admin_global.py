#!/usr/bin/env python3
"""
Promove (ou rebaixa) um usuário para/de admin_global.

Uso (a partir da raiz do projeto):
    python scripts/promover_admin_global.py --email fulano@dtx.aero
    python scripts/promover_admin_global.py --email fulano@dtx.aero --rebaixar
    python scripts/promover_admin_global.py --email fulano@dtx.aero --dry-run
"""

import argparse
import os
import sys

_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _raiz)

from app.models_usuario import Usuario  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Promove ou rebaixa usuário para/de admin_global.")
    parser.add_argument("--email", required=True, help="E-mail do usuário alvo")
    parser.add_argument(
        "--rebaixar",
        action="store_true",
        help="Rebaixa admin_global → admin (sem flag: promove → admin_global)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas simula; não grava no Firestore",
    )
    args = parser.parse_args()

    usuario = Usuario.get_by_email(args.email)
    if not usuario:
        print(f"[ERRO] Usuário não encontrado: {args.email}")
        sys.exit(1)

    perfil_atual = usuario.perfil
    if args.rebaixar:
        if perfil_atual != "admin_global":
            print(
                f"[ERRO] Usuário '{args.email}' não é admin_global (perfil atual: {perfil_atual})"
            )
            sys.exit(1)
        novo_perfil = "admin"
        acao = "Rebaixar"
    else:
        if perfil_atual == "admin_global":
            print(f"[INFO] Usuário '{args.email}' já é admin_global. Nenhuma alteração.")
            sys.exit(0)
        if perfil_atual not in ("admin", "supervisor"):
            print(
                f"[AVISO] Perfil atual '{perfil_atual}' não é admin nem supervisor. "
                "Recomenda-se promover um admin ou supervisor existente."
            )
        novo_perfil = "admin_global"
        acao = "Promover"

    print(f"\n{acao}: {usuario.nome} ({args.email})")
    print(f"  Perfil atual : {perfil_atual}")
    print(f"  Novo perfil  : {novo_perfil}")

    if args.dry_run:
        print("\n[DRY-RUN] Nenhuma alteração gravada.")
        return

    confirmacao = input("\nConfirmar? (s/N): ").strip().lower()
    if confirmacao != "s":
        print("Operação cancelada.")
        sys.exit(0)

    usuario.update(perfil=novo_perfil)
    print(f"\n[OK] Perfil atualizado para '{novo_perfil}' com sucesso.")


if __name__ == "__main__":
    main()
