#!/usr/bin/env python3
"""
Correção pontual: inclui julia.salgado@dtx.aero como observadora do chamado
CHM-0003, aberto por outro setor com destino "Produção" antes da regra
automática nesse sentido (extensão de 2026-08-18 da regra de 2026-08-17)
estar implementada. Ela não recebeu a notificação de observadora no momento
da criação.

Uso (a partir da raiz do projeto, dentro do container da app):
    python scripts/incluir_julia_chm0003.py --dry-run
    python scripts/incluir_julia_chm0003.py
"""

import argparse
import os
import sys

_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _raiz)

from app import create_app  # noqa: E402
from app import db as db_module  # noqa: E402
from app.db.models.chamado import ChamadoRow  # noqa: E402
from app.models import Chamado  # noqa: E402
from app.models_historico import Historico  # noqa: E402
from app.models_usuario import Usuario  # noqa: E402

NUMERO_CHAMADO = "CHM-0003"
AREA_ESPERADA = "Produção"
EMAIL_JULIA = "julia.salgado@dtx.aero"
USUARIO_ID_SISTEMA = "sistema"
USUARIO_NOME_SISTEMA = "Sistema (correção retroativa observador Produção)"


def _buscar_id_por_numero(numero: str) -> str | None:
    with db_module.SessionLocal() as session:
        row = session.query(ChamadoRow).filter(ChamadoRow.numero_chamado == numero).first()
        return row.id if row else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"Inclui {EMAIL_JULIA} como observadora do chamado {NUMERO_CHAMADO}."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas mostra o que seria alterado; não grava no banco nem notifica",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        _executar(args.dry_run)


def _executar(dry_run: bool) -> None:
    chamado_id = _buscar_id_por_numero(NUMERO_CHAMADO)
    if not chamado_id:
        print(f"[ERRO] Chamado {NUMERO_CHAMADO} não encontrado.")
        sys.exit(1)

    chamado = Chamado.get_by_id(chamado_id)
    if not chamado:
        print(f"[ERRO] Falha ao carregar chamado {chamado_id}.")
        sys.exit(1)

    print(f"\nChamado: {chamado.numero_chamado} ({chamado.id})")
    print(f"  Área: {chamado.area}")
    print(f"  Solicitante: {chamado.solicitante_nome}")
    print(f"  Categoria: {chamado.categoria}")
    print(f"  Observadores atuais: {[o.get('email') for o in chamado.observadores]}")

    if chamado.area != AREA_ESPERADA:
        print(
            f"\n[AVISO] Área do chamado é '{chamado.area}', esperado '{AREA_ESPERADA}'. "
            "Abortando por segurança — confirme o número do chamado."
        )
        sys.exit(1)

    if any(o.get("email") == EMAIL_JULIA for o in chamado.observadores):
        print("\n[INFO] Julia já está nos observadores. Nenhuma alteração.")
        return

    julia = Usuario.get_by_email(EMAIL_JULIA)
    if not julia:
        print(f"\n[ERRO] Conta {EMAIL_JULIA} não encontrada.")
        sys.exit(1)

    novo_observador = {"usuario_id": julia.id, "nome": julia.nome, "email": julia.email}
    print(f"\n  Nova observadora: {julia.nome} ({julia.email})")

    if dry_run:
        print("\n[DRY-RUN] Nenhuma alteração gravada.")
        return

    chamado.observadores = [*chamado.observadores, novo_observador]
    if not chamado.salvar():
        print("\n[ERRO] Falha ao salvar chamado.")
        sys.exit(1)

    Historico(
        chamado_id=chamado.id,
        usuario_id=USUARIO_ID_SISTEMA,
        usuario_nome=USUARIO_NOME_SISTEMA,
        acao="inclusao_observadores",
        campo_alterado="observadores",
        valor_anterior=None,
        valor_novo=julia.nome,
        detalhe="Correção retroativa — regra automática Produção como destino",
    ).save()

    from app.services.chamado_notificacao_service import notificar_observadores_criacao

    notificar_observadores_criacao(
        chamado_id=chamado.id,
        numero_chamado=chamado.numero_chamado,
        categoria=chamado.categoria or "",
        solicitante_nome=chamado.solicitante_nome,
        observadores=[novo_observador],
    )

    print("\n[OK] Julia incluída como observadora e notificada.")


if __name__ == "__main__":
    main()
