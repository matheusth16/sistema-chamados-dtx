#!/usr/bin/env python3
"""Semeia usuários e chamados de demonstração para captura de screenshots do onboarding.

Cria 4 usuários fake (um por perfil, incluindo admin_global) e alguns chamados
fake com status variados, para que as telas capturadas pelo Playwright
(tests/e2e/test_capture_onboarding_screenshots.py) não exponham dados reais
de usuários/chamados da DTX.

Uso:
    python scripts/seed/seed_dados_demo_onboarding.py            # cria/atualiza os dados demo
    python scripts/seed/seed_dados_demo_onboarding.py --limpar   # remove os dados demo
"""

import argparse
import os
import sys

_raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _raiz)

from app.database import db  # noqa: E402
from app.models import Chamado  # noqa: E402
from app.models_categorias import CategoriaSetor  # noqa: E402
from app.models_usuario import Usuario  # noqa: E402
from app.utils import gerar_numero_chamado  # noqa: E402

SENHA_DEMO = "DemoOnboarding123!"
AREA_DEMO = "Demo"

# Fallback usado apenas se nenhum setor estiver configurado em /admin/categorias
# (instalação nova, sem categorias cadastradas ainda).
SETORES_FALLBACK = ["TI", "Manutencao", "RH", "Qualidade"]


def _setores_disponiveis() -> list[str]:
    """Usa os setores realmente configurados no Firestore (evita categorias
    inexistentes nesta instalação); cai para uma lista genérica se vazio."""
    try:
        setores = [s.nome_pt for s in CategoriaSetor.get_all() if s.nome_pt]
    except Exception:
        setores = []
    return setores or SETORES_FALLBACK


USUARIOS_DEMO = [
    {
        "id": "demo_solicitante",
        "email": "demo.solicitante@dtx.com",
        "nome": "Solicitante Demo",
        "perfil": "solicitante",
        "areas": [],
    },
    {
        "id": "demo_supervisor",
        "email": "demo.supervisor@dtx.com",
        "nome": "Supervisor Demo",
        "perfil": "supervisor",
        "areas": [AREA_DEMO],
    },
    {
        "id": "demo_admin",
        "email": "demo.admin@dtx.com",
        "nome": "Admin Demo",
        "perfil": "admin",
        "areas": [AREA_DEMO],
    },
    {
        "id": "demo_admin_global",
        "email": "demo.admin.global@dtx.com",
        "nome": "Admin Global Demo",
        "perfil": "admin_global",
        "areas": [AREA_DEMO],
    },
]

CHAMADOS_DEMO = [
    {
        "tipo_solicitacao": "Acesso a Sistema",
        "descricao": "Chamado demo — solicitação de acesso ao sistema X para novo colaborador.",
        "status": "Aberto",
        "prioridade": 2,
    },
    {
        "tipo_solicitacao": "Reparo",
        "descricao": "Chamado demo — equipamento apresentando ruído incomum na linha de produção.",
        "status": "Em Atendimento",
        "prioridade": 1,
    },
    {
        "tipo_solicitacao": "Documentação",
        "descricao": "Chamado demo — solicitação de declaração para fins de comprovação de renda.",
        "status": "Concluído",
        "prioridade": 3,
    },
    {
        "tipo_solicitacao": "Equipamento",
        "descricao": "Chamado demo — solicitação de notebook adicional para o setor.",
        "status": "Cancelado",
        "prioridade": 3,
        "motivo_cancelamento": "Chamado demo cancelado — necessidade não confirmada.",
    },
    {
        "tipo_solicitacao": "Não Conformidade",
        "descricao": "Chamado demo — não conformidade identificada em lote de peças recebido.",
        "status": "Aberto",
        "prioridade": 1,
    },
    {
        "tipo_solicitacao": "Preventiva",
        "descricao": "Chamado demo — manutenção preventiva agendada para próxima parada de linha.",
        "status": "Em Atendimento",
        "prioridade": 2,
    },
]


def _upsert_usuario(dados: dict) -> None:
    existente = Usuario.get_by_email(dados["email"])
    usuario = existente or Usuario(
        id=dados["id"],
        email=dados["email"],
        nome=dados["nome"],
        perfil=dados["perfil"],
        areas=dados["areas"],
    )
    usuario.nome = dados["nome"]
    usuario.perfil = dados["perfil"]
    usuario.areas = dados["areas"]
    usuario.must_change_password = False
    usuario.onboarding_perfis_vistos = [dados["perfil"]]
    usuario.onboarding_passo = 0
    usuario.set_password(SENHA_DEMO)
    usuario.save()
    print(f"  Usuário demo pronto: {dados['email']} (perfil={dados['perfil']}, senha={SENHA_DEMO})")


def _criar_chamados_demo() -> None:
    solicitante = Usuario.get_by_email("demo.solicitante@dtx.com")
    supervisor = Usuario.get_by_email("demo.supervisor@dtx.com")
    if not solicitante or not supervisor:
        print("  Usuários demo ausentes — rode o seed de usuários primeiro.")
        return

    existentes = list(
        db.collection("chamados").where("solicitante_id", "==", solicitante.id).stream()
    )
    if existentes:
        print(f"  {len(existentes)} chamados demo já existem — pulando criação (idempotente).")
        return

    setores = _setores_disponiveis()
    for i, dados in enumerate(CHAMADOS_DEMO):
        numero_chamado = gerar_numero_chamado()
        chamado = Chamado(
            numero_chamado=numero_chamado,
            categoria=setores[i % len(setores)],
            tipo_solicitacao=dados["tipo_solicitacao"],
            descricao=dados["descricao"],
            responsavel=supervisor.nome,
            responsavel_id=supervisor.id,
            solicitante_id=solicitante.id,
            solicitante_nome=solicitante.nome,
            area=AREA_DEMO,
            status=dados["status"],
            prioridade=dados["prioridade"],
            motivo_cancelamento=dados.get("motivo_cancelamento"),
        )
        db.collection("chamados").add(chamado.to_dict())
        print(f"  Chamado demo criado: {numero_chamado} ({dados['status']})")


def _limpar_dados_demo() -> None:
    for dados in USUARIOS_DEMO:
        db.collection("usuarios").document(dados["id"]).delete()
        print(f"  Usuário demo removido: {dados['email']}")

    solicitante_id = "demo_solicitante"
    chamados = list(
        db.collection("chamados").where("solicitante_id", "==", solicitante_id).stream()
    )
    for doc in chamados:
        doc.reference.delete()
    print(f"  {len(chamados)} chamados demo removidos.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limpar",
        action="store_true",
        help="Remove os usuários e chamados demo em vez de criá-los.",
    )
    args = parser.parse_args()

    if args.limpar:
        print("Removendo dados de demonstração do onboarding...")
        _limpar_dados_demo()
        print("Concluído.")
        return

    print("Semeando usuários de demonstração...")
    for dados in USUARIOS_DEMO:
        _upsert_usuario(dados)

    print("Semeando chamados de demonstração...")
    _criar_chamados_demo()

    print("\nConcluído. Credenciais para captura de screenshots (.env.test):")
    for dados in USUARIOS_DEMO:
        print(f"  {dados['perfil']}: {dados['email']} / {SENHA_DEMO}")


if __name__ == "__main__":
    main()
