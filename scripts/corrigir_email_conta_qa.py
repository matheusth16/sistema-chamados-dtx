#!/usr/bin/env python3
"""
Corrige o e-mail da conta de teste qa_matheus_costa no banco de DEV LOCAL,
que ficou cadastrada com o e-mail de trabalho real do usuário em vez de um
endereço fictício.

Motivo: a conta foi criada manualmente numa sessão de QA anterior, direto
no banco, sem passar por nenhum script de seed versionado. Isso causou o
envio de um e-mail real de "lembrete de MFA pendente" em 2026-08-17, já
que o dev local usa credenciais reais do Microsoft Graph API. As outras
12 contas QA seguem o padrão fictício qa.<papel>@dtx.aero; este script
alinha essa conta ao mesmo padrão.

Uso (a partir da raiz do projeto):
    python scripts/corrigir_email_conta_qa.py --dry-run
    python scripts/corrigir_email_conta_qa.py
"""

import argparse
import os
import sys

_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _raiz)

from app import create_app  # noqa: E402
from app.models_usuario import Usuario  # noqa: E402

ID_ALVO = "qa_matheus_costa"
EMAIL_NOVO = "qa.matheus.costa@dtx.aero"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Troca o e-mail real da conta de teste qa_matheus_costa por um fictício."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas mostra o que seria alterado; não grava no banco",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        _executar(args.dry_run)


def _executar(dry_run: bool) -> None:
    usuario = Usuario.get_by_id(ID_ALVO)
    if not usuario:
        print(f"[ERRO] Usuário não encontrado: {ID_ALVO}")
        sys.exit(1)

    print(f"\nConta: {usuario.nome} ({usuario.id})")
    print(f"  E-mail atual: {usuario.email}")
    print(f"  E-mail novo : {EMAIL_NOVO}")

    if usuario.email == EMAIL_NOVO:
        print("\n[INFO] Já está com o e-mail fictício. Nenhuma alteração.")
        return

    if dry_run:
        print("\n[DRY-RUN] Nenhuma alteração gravada.")
        return

    if not usuario.update(email=EMAIL_NOVO):
        print("\n[ERRO] Falha ao atualizar o e-mail.")
        sys.exit(1)

    print("\n[OK] E-mail atualizado com sucesso.")


if __name__ == "__main__":
    main()
