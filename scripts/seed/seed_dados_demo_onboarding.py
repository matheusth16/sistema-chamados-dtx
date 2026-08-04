#!/usr/bin/env python3
"""Semeia usuários e chamados de demonstração para captura de screenshots do onboarding.

Cria 4 usuários fake (um por perfil, incluindo admin_global) e alguns chamados
fake com status variados, para que as telas capturadas pelo Playwright
(tests/e2e/test_capture_onboarding_screenshots.py) não exponham dados reais
de usuários/chamados da DTX.

Uso:
    python scripts/seed/seed_dados_demo_onboarding.py            # cria/atualiza os dados demo
    python scripts/seed/seed_dados_demo_onboarding.py --limpar   # remove os dados demo

Requer DATABASE_URL apontando pro Postgres de destino (dev local, nunca produção).
"""

import argparse
import os
import sys
from datetime import datetime

_raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _raiz)

# Console do Windows (cp1252) não decodifica os acentos usados nas mensagens
# abaixo — força UTF-8 na saída pra rodar sem virar "?" localmente.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from flask import Flask  # noqa: E402

from app import db as db_module  # noqa: E402
from app.db import normalizar_url_driver  # noqa: E402


def _init_db_module() -> None:
    """Inicializa app.db.engine/SessionLocal sem precisar de create_app() —
    este script nunca sobe a app Flask inteira (evita disparar o scheduler)."""
    if db_module.SessionLocal is not None:
        return
    from sqlalchemy import create_engine
    from sqlalchemy.orm import scoped_session, sessionmaker

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL não configurada — necessária pra semear dados de dev")
    db_module.engine = create_engine(normalizar_url_driver(database_url), pool_pre_ping=True)
    db_module.SessionLocal = scoped_session(
        sessionmaker(bind=db_module.engine, autoflush=False, expire_on_commit=False)
    )


_init_db_module()

from app.db.models.chamado import ChamadoRow  # noqa: E402
from app.models import Chamado  # noqa: E402
from app.models_categorias import CategoriaSetor  # noqa: E402
from app.models_usuario import Usuario  # noqa: E402
from app.utils import gerar_numero_chamado  # noqa: E402

# current_app.logger é usado só no fallback de erro de gerar_numero_chamado() —
# contexto mínimo, sem os efeitos colaterais de create_app() (scheduler etc.)
_ctx_app = Flask(__name__)

SENHA_DEMO = "DemoOnboarding123!"
AREA_DEMO = "Demo"

# Fallback usado apenas se nenhum setor estiver configurado em /admin/categorias
# (instalação nova, sem categorias cadastradas ainda).
SETORES_FALLBACK = ["TI", "Manutencao", "RH", "Qualidade"]


def _setores_disponiveis() -> list[str]:
    """Usa os setores realmente configurados no Postgres (evita categorias
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
        "totp_env": "TEST_SOLICITANTE_TOTP_SECRET",
    },
    {
        "id": "demo_supervisor",
        "email": "demo.supervisor@dtx.com",
        "nome": "Supervisor Demo",
        "perfil": "supervisor",
        "areas": [AREA_DEMO],
        "totp_env": "TEST_SUPERVISOR_TOTP_SECRET",
    },
    {
        "id": "demo_admin",
        "email": "demo.admin@dtx.com",
        "nome": "Admin Demo",
        "perfil": "admin",
        "areas": [AREA_DEMO],
        "totp_env": "TEST_ADMIN_TOTP_SECRET",
    },
    {
        "id": "demo_admin_global",
        "email": "demo.admin.global@dtx.com",
        "nome": "Admin Global Demo",
        "perfil": "admin_global",
        "areas": [AREA_DEMO],
        "totp_env": "TEST_ADMIN_GLOBAL_TOTP_SECRET",
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
    """MFA é obrigatório em todo login (ver app/routes/auth.py) — sem
    mfa_enabled/mfa_secret configurados aqui, o login cairia na tela de setup
    forçado em vez de aceitar o código TOTP que TEST_*_TOTP_SECRET (.env.test)
    já documenta pra essas mesmas contas."""
    totp_secret = os.environ.get(dados["totp_env"], "").strip()

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
    if totp_secret:
        usuario.mfa_enabled = True
        usuario.mfa_secret = totp_secret
    usuario.save()
    mfa_info = (
        "MFA configurado" if totp_secret else "MFA NÃO configurado (sem TOTP_SECRET no ambiente)"
    )
    print(
        f"  Usuário demo pronto: {dados['email']} (perfil={dados['perfil']}, "
        f"senha={SENHA_DEMO}, {mfa_info})"
    )


def _criar_chamados_demo() -> None:
    from sqlalchemy import select

    solicitante = Usuario.get_by_email("demo.solicitante@dtx.com")
    supervisor = Usuario.get_by_email("demo.supervisor@dtx.com")
    if not solicitante or not supervisor:
        print("  Usuários demo ausentes — rode o seed de usuários primeiro.")
        return

    with db_module.SessionLocal() as session:
        existentes = session.execute(
            select(ChamadoRow.id).where(ChamadoRow.solicitante_id == solicitante.id)
        ).first()
    if existentes:
        print("  Chamados demo já existem — pulando criação (idempotente).")
        return

    setores = _setores_disponiveis()
    with _ctx_app.app_context():
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
            row_kwargs = chamado.to_row_kwargs()
            row_kwargs["data_abertura"] = datetime.now()
            with db_module.SessionLocal() as session, session.begin():
                session.add(ChamadoRow(**row_kwargs))
            print(f"  Chamado demo criado: {numero_chamado} ({dados['status']})")


def _limpar_dados_demo() -> None:
    for dados in USUARIOS_DEMO:
        usuario = Usuario.get_by_email(dados["email"])
        if usuario:
            usuario.delete()
        print(f"  Usuário demo removido: {dados['email']}")

    from sqlalchemy import select

    with db_module.SessionLocal() as session, session.begin():
        rows = (
            session.execute(
                select(ChamadoRow).where(ChamadoRow.solicitante_id == "demo_solicitante")
            )
            .scalars()
            .all()
        )
        for row in rows:
            session.delete(row)
        count = len(rows)
    print(f"  {count} chamados demo removidos.")


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
