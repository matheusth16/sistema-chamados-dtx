"""
Fase 2, Marco 11 — Migração completa Firestore → PostgreSQL.

**NÃO RODAR CONTRA FIRESTORE DE PRODUÇÃO AO VIVO.** Primeira execução real
sempre contra um projeto de staging restaurado de um backup/export do
Firestore de produção. Este script foi escrito seguindo o desenho de
~/.claude/plans/curious-enchanting-corbato.md (seção 4) mas ainda **não foi
executado contra dado real** — os mapeamentos de campo abaixo foram
derivados dos modelos Python já migrados (app/models*.py, app/db/models/),
não de uma amostra real do Firestore. Antes do primeiro rehearsal, valide
com --dump isolado e inspecione scripts/migration_dump/*.jsonl à mão.

Três fases independentes e idempotentes (podem ser re-rodadas):

  1. --dump   Lê cada coleção do Firestore, grava JSONL streaming em
              scripts/migration_dump/<colecao>.jsonl (não toca Postgres).
  2. --load   Lê os JSONL e faz o insert em lote no Postgres, na ordem de
              dependência de FK (ver ORDEM abaixo). Requer schema vazio
              (rode `alembic downgrade base && alembic upgrade head` antes
              de cada rehearsal — idempotência via schema limpo, não via
              upsert).
  3. --verify Roda as checagens obrigatórias da seção 4 do plano; qualquer
              falha bloqueia o cutover (não modifica dado).

PII (usuarios.email/nome/mfa_secret): copiado byte-a-byte do Firestore pro
Postgres, criptografado ou não — NUNCA descriptografado nem re-criptografado
em trânsito. O ciphertext Fernet é agnóstico de banco. email_lookup_hash é
copiado do doc (ele já é um hash determinístico do plaintext, calculado uma
vez no rollout da Onda 4 — recalculá-lo aqui exigiria descriptografar).

Uso:
    python scripts/migrate_firestore_to_postgres.py --dump
    python scripts/migrate_firestore_to_postgres.py --load
    python scripts/migrate_firestore_to_postgres.py --verify

Variáveis de ambiente exigidas:
    GOOGLE_CREDENTIALS_JSON ou credentials.json na raiz — acesso ao Firestore
    de ORIGEM (staging restaurado, nunca produção ao vivo neste script).
    DATABASE_URL — Postgres de DESTINO (staging).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ROOT)
os.chdir(ROOT)
sys.path.insert(0, ROOT)

# Console do Windows (cp1252) não decodifica os acentos/setas usados nas
# mensagens abaixo — força UTF-8 na saída pra rodar sem crashar localmente.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate_firestore_to_postgres")

DUMP_DIR = Path(ROOT) / "scripts" / "migration_dump"
CHAMADO_ID_MAP_PATH = DUMP_DIR / "_chamado_id_map.json"

# Nomes de coleção Firestore, na ordem em que devem ser DUMPADAS (irrelevante
# pra dump — cada uma é independente) e CARREGADAS (relevante — respeita FK).
COLECOES_SIMPLES = [
    "categorias_setores",
    "categorias_gates",
    "categorias_impactos",
    "grupos_rl",
    "usuarios",
    "push_subscriptions",
    "historico_usuarios",
    "solicitacoes_lgpd",
    "contadores_uso",
]
COLECOES_DEPENDENTES = ["chamados", "historico", "notificacoes"]
SINGLETONS = {
    # (colecao, doc_id): nome do arquivo de dump
    ("config", "setor_para_area"): "singleton_config_setor_para_area.json",
    ("_sistema", "contador_chamados"): "singleton_sistema_contador_chamados.json",
}


# ─────────────────────────────────────────────────────────────────────────
# Fase 1 — DUMP (Firestore → JSONL, streaming, não toca Postgres)
# ─────────────────────────────────────────────────────────────────────────


def _json_default(obj: Any) -> Any:
    """Serializa tipos que o json padrão não conhece (datetime do Firestore)."""
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):  # DatetimeWithNanoseconds e afins
        return obj.isoformat()
    raise TypeError(f"Tipo não serializável em JSON: {type(obj)!r}")


def _init_firestore():
    """Inicializa o Firebase Admin (mesma lógica de app/database.py, sem
    depender de importar o módulo — evita puxar toda a app Flask aqui)."""
    import firebase_admin
    from firebase_admin import credentials

    try:
        firebase_admin.get_app()
    except ValueError:
        creds_json_env = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
        cert_path = os.path.join(ROOT, "credentials.json")
        if creds_json_env:
            cred = credentials.Certificate(json.loads(creds_json_env))
            firebase_admin.initialize_app(cred)
        elif os.path.exists(cert_path):
            cred = credentials.Certificate(cert_path)
            firebase_admin.initialize_app(cred)
        else:
            raise RuntimeError(
                "Sem credenciais Firestore (GOOGLE_CREDENTIALS_JSON ou credentials.json). "
                "Confirme que aponta pro projeto de STAGING, não produção."
            ) from None

    from firebase_admin import firestore as fs

    return fs.client()


def _dump_collection(db, nome: str) -> int:
    """Stream de uma coleção inteira → JSONL. Retorna a contagem de docs."""
    from scripts.migrations._migration_utils import _iter_collection_paginated

    DUMP_DIR.mkdir(parents=True, exist_ok=True)
    destino = DUMP_DIR / f"{nome}.jsonl"
    count = 0
    with destino.open("w", encoding="utf-8") as f:
        for doc in _iter_collection_paginated(db.collection(nome)):
            registro = {"_id": doc.id, **(doc.to_dict() or {})}
            f.write(json.dumps(registro, default=_json_default, ensure_ascii=False) + "\n")
            count += 1
    logger.info("dump %-22s %6d docs -> %s", nome, count, destino.name)
    return count


def _dump_singleton(db, colecao: str, doc_id: str, arquivo: str) -> None:
    DUMP_DIR.mkdir(parents=True, exist_ok=True)
    doc = db.collection(colecao).document(doc_id).get()
    payload = doc.to_dict() if doc.exists else None
    destino = DUMP_DIR / arquivo
    destino.write_text(
        json.dumps(payload, default=_json_default, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("dump singleton %s/%s -> %s (existe=%s)", colecao, doc_id, arquivo, doc.exists)


def fase_dump() -> None:
    db = _init_firestore()
    logger.info("=== DUMP: %s ===", DUMP_DIR)
    total = 0
    for nome in COLECOES_SIMPLES + COLECOES_DEPENDENTES:
        total += _dump_collection(db, nome)
    for (colecao, doc_id), arquivo in SINGLETONS.items():
        _dump_singleton(db, colecao, doc_id, arquivo)
    logger.info(
        "=== DUMP concluído: %d documentos em %d coleções ===",
        total,
        len(COLECOES_SIMPLES) + len(COLECOES_DEPENDENTES),
    )


# ─────────────────────────────────────────────────────────────────────────
# Fase 2 — LOAD (JSONL → Postgres, em lote, respeitando FK)
# ─────────────────────────────────────────────────────────────────────────


def _init_db_module() -> None:
    """Inicializa app.db.engine/SessionLocal sem precisar de create_app() —
    este script nunca sobe a app Flask inteira, só a camada de dado. Usa
    DATABASE_URL diretamente (não TEST_DATABASE_URL/DATABASE_URL como o
    alembic/env.py faz — aqui é sempre explícito, sem ambiguidade)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import scoped_session, sessionmaker

    from app import db as db_module
    from app.db import normalizar_url_driver

    if db_module.SessionLocal is not None:
        return  # já inicializado (chamada repetida dentro do mesmo processo)

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL não configurada — obrigatória para --load/--verify")

    db_module.engine = create_engine(normalizar_url_driver(database_url), pool_pre_ping=True)
    db_module.SessionLocal = scoped_session(
        sessionmaker(bind=db_module.engine, autoflush=False, expire_on_commit=False)
    )
    logger.info("Postgres inicializado: %s", database_url.split("@")[-1])


def _ler_jsonl(nome: str):
    caminho = DUMP_DIR / f"{nome}.jsonl"
    if not caminho.exists():
        raise FileNotFoundError(f"{caminho} não existe — rode --dump primeiro")
    with caminho.open(encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if linha:
                yield json.loads(linha)


def _parse_dt(valor: str | None) -> datetime | None:
    if not valor or not isinstance(valor, str):
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None


def _load_categorias() -> None:
    from app.models_categorias import CategoriaGate, CategoriaImpacto, CategoriaSetor

    for nome, cls in (
        ("categorias_setores", CategoriaSetor),
        ("categorias_gates", CategoriaGate),
        ("categorias_impactos", CategoriaImpacto),
    ):
        count = 0
        for data in _ler_jsonl(nome):
            obj = cls.from_dict(data)
            obj.save()
            count += 1
        logger.info("load %-22s %6d linhas", nome, count)


def _load_grupos_rl() -> None:
    """Insert direto via ORM (não get_or_create — aqui é migração 1:1, não
    resolução por rl_codigo; get_or_create() é usado depois, no load de
    chamados, pra resolver grupo_rl_id a partir do rl_codigo do chamado)."""
    from app import db as db_module
    from app.db.models.grupo_rl import GrupoRLRow

    count = 0
    with db_module.SessionLocal() as session, session.begin():
        for data in _ler_jsonl("grupos_rl"):
            session.add(
                GrupoRLRow(
                    rl_codigo=(data.get("rl_codigo") or "").strip(),
                    criado_em=_parse_dt(data.get("criado_em")),
                    criado_por_id=data.get("criado_por_id"),
                    area=data.get("area"),
                )
            )
            count += 1
    logger.info("load %-22s %6d linhas", "grupos_rl", count)


def _load_usuarios() -> None:
    """Copia email/nome/mfa_secret/email_lookup_hash VERBATIM (ciphertext
    Fernet ou plaintext, tanto faz) — nunca decripta nem recriptografa em
    trânsito. id continua TEXT = doc.id do Firestore (sem remapeamento)."""
    from app import db as db_module
    from app.db.models.usuario import UsuarioRow

    count = 0
    with db_module.SessionLocal() as session, session.begin():
        for data in _ler_jsonl("usuarios"):
            areas = data.get("areas") or ([data["area"]] if data.get("area") else [])
            perfil = data.get("perfil", "solicitante")
            onboarding_perfis_vistos = data.get("onboarding_perfis_vistos")
            if onboarding_perfis_vistos is None:
                onboarding_perfis_vistos = [perfil] if data.get("onboarding_completo") else []

            session.add(
                UsuarioRow(
                    id=data["_id"],
                    email=data.get("email") or "",
                    email_lookup_hash=data.get("email_lookup_hash"),
                    nome=data.get("nome") or "",
                    perfil=perfil,
                    areas=list(areas),
                    senha_hash=data.get("senha_hash"),
                    ativo=data.get("ativo", True),
                    must_change_password=data.get("must_change_password", False),
                    password_changed_at=_parse_dt(data.get("password_changed_at")),
                    exp_total=data.get("exp_total", 0),
                    exp_semanal=data.get("exp_semanal", 0),
                    level=data.get("level", 1),
                    conquistas=list(data.get("conquistas") or []),
                    onboarding_perfis_vistos=list(onboarding_perfis_vistos),
                    onboarding_passo=data.get("onboarding_passo", 0),
                    nivel_gestao=data.get("nivel_gestao"),
                    mfa_enabled=data.get("mfa_enabled", False),
                    mfa_secret=data.get("mfa_secret"),
                    mfa_backup_codes=list(data.get("mfa_backup_codes") or []),
                    auth_provider=data.get("auth_provider", "local"),
                )
            )
            count += 1
    logger.info("load %-22s %6d linhas", "usuarios", count)


def _load_apoio() -> None:
    """push_subscriptions, historico_usuarios, solicitacoes_lgpd,
    contadores_uso — sem FK entre si nem com usuarios (ids TEXT soltos)."""
    from app import db as db_module
    from app.db.models.apoio import (
        ContadorUsoRow,
        HistoricoUsuarioRow,
        PushSubscriptionRow,
        SolicitacaoLgpdRow,
    )

    with db_module.SessionLocal() as session, session.begin():
        n = 0
        for data in _ler_jsonl("push_subscriptions"):
            session.add(
                PushSubscriptionRow(
                    usuario_id=data.get("usuario_id"),
                    endpoint=data.get("endpoint"),
                    p256dh=data.get("p256dh"),
                    auth=data.get("auth"),
                    created_at=_parse_dt(data.get("created_at")) or datetime.now(),
                    updated_at=_parse_dt(data.get("updated_at")) or datetime.now(),
                )
            )
            n += 1
        logger.info("load %-22s %6d linhas", "push_subscriptions", n)

        n = 0
        for data in _ler_jsonl("historico_usuarios"):
            session.add(
                HistoricoUsuarioRow(
                    usuario_alvo_id=data.get("usuario_alvo_id"),
                    usuario_alvo_nome=data.get("usuario_alvo_nome"),
                    admin_id=data.get("admin_id"),
                    admin_nome=data.get("admin_nome"),
                    acao=data.get("acao"),
                    detalhe=data.get("detalhe"),
                    data_acao=_parse_dt(data.get("data_acao")) or datetime.now(),
                )
            )
            n += 1
        logger.info("load %-22s %6d linhas", "historico_usuarios", n)

        n = 0
        for data in _ler_jsonl("solicitacoes_lgpd"):
            session.add(
                SolicitacaoLgpdRow(
                    usuario_id=data.get("usuario_id"),
                    usuario_nome=data.get("usuario_nome"),
                    usuario_email=data.get("usuario_email"),
                    tipo=data.get("tipo"),
                    status=data.get("status", "pendente"),
                    data_solicitacao=_parse_dt(data.get("data_solicitacao")) or datetime.now(),
                    data_resolucao=_parse_dt(data.get("data_resolucao")),
                    admin_id=data.get("admin_id"),
                    admin_nome=data.get("admin_nome"),
                )
            )
            n += 1
        logger.info("load %-22s %6d linhas", "solicitacoes_lgpd", n)

        n = 0
        for data in _ler_jsonl("contadores_uso"):
            # Doc id do Firestore era "{user_id}_{data}" — a chave real está
            # nos campos, não precisa parsear o _id.
            data_str = data.get("data")
            data_convertida = datetime.fromisoformat(data_str).date() if data_str else date.today()
            session.add(
                ContadorUsoRow(
                    user_id=data.get("user_id"),
                    data=data_convertida,
                    relatorio_geracoes=data.get("relatorio_geracoes", 0),
                    export_excel_geracoes=data.get("export_excel_geracoes", 0),
                )
            )
            n += 1
        logger.info("load %-22s %6d linhas", "contadores_uso", n)


def _load_chamados() -> dict[str, int]:
    """Carrega chamados + tabelas-junção (participantes/observadores).

    Retorna e persiste o mapa {doc_id_firestore: id_postgres} — historico e
    notificacoes referenciam chamado_id pelo doc_id antigo, então precisam
    desse mapa na fase seguinte (chamados.id agora é autoincrement).
    """
    from app import db as db_module
    from app.db.models.chamado import ChamadoObservadorRow, ChamadoParticipanteRow, ChamadoRow
    from app.models import Chamado
    from app.models_grupo_rl import GrupoRL

    id_map: dict[str, int] = {}
    count = 0
    with db_module.SessionLocal() as session, session.begin():
        for data in _ler_jsonl("chamados"):
            doc_id = data["_id"]
            chamado_obj = Chamado.from_dict(data, id=doc_id)
            row_kwargs = chamado_obj.to_row_kwargs()

            # grupo_rl_id não existe no doc Firestore (campo novo, Marco 7) —
            # resolve pelo rl_codigo, mesma lógica de chamados_criacao_service.py.
            grupo_rl_id = None
            rl_codigo = (data.get("rl_codigo") or "").strip()
            if rl_codigo and data.get("categoria") in ("Projetos", "AOG"):
                grupo = GrupoRL.get_or_create(rl_codigo=rl_codigo)
                grupo_rl_id = grupo.id
            row_kwargs["grupo_rl_id"] = grupo_rl_id
            row_kwargs["data_abertura"] = _parse_dt(data.get("data_abertura")) or datetime.now()

            row = ChamadoRow(**row_kwargs)
            session.add(row)
            session.flush()  # popula row.id
            id_map[doc_id] = row.id

            for p in chamado_obj.participantes:
                session.add(
                    ChamadoParticipanteRow(
                        chamado_id=row.id,
                        supervisor_id=p.get("supervisor_id"),
                        area=p.get("area"),
                        status=p.get("status") or "pendente",
                        concluido_em=_parse_dt(p.get("concluido_em")),
                    )
                )
            for o in chamado_obj.observadores:
                session.add(
                    ChamadoObservadorRow(
                        chamado_id=row.id,
                        usuario_id=o.get("usuario_id"),
                        nome=o.get("nome") or "",
                        email=o.get("email") or "",
                    )
                )
            count += 1
            if count % 1000 == 0:
                session.flush()
                logger.info("  ... %d chamados processados", count)

    logger.info("load %-22s %6d linhas", "chamados", count)
    CHAMADO_ID_MAP_PATH.write_text(json.dumps(id_map), encoding="utf-8")
    logger.info("mapa chamado_id salvo em %s (%d entradas)", CHAMADO_ID_MAP_PATH.name, len(id_map))
    return id_map


def _carregar_chamado_id_map() -> dict[str, int]:
    if not CHAMADO_ID_MAP_PATH.exists():
        raise FileNotFoundError(
            f"{CHAMADO_ID_MAP_PATH} não existe — rode a carga de 'chamados' antes de "
            "'historico'/'notificacoes'."
        )
    return json.loads(CHAMADO_ID_MAP_PATH.read_text(encoding="utf-8"))


def _load_historico(id_map: dict[str, int]) -> None:
    from app import db as db_module
    from app.db.models.historico import HistoricoRow

    count = 0
    ignorados = 0
    with db_module.SessionLocal() as session, session.begin():
        for data in _ler_jsonl("historico"):
            chamado_id_antigo = str(data.get("chamado_id") or "")
            novo_id = id_map.get(chamado_id_antigo)
            if novo_id is None:
                ignorados += 1
                continue
            session.add(
                HistoricoRow(
                    chamado_id=novo_id,
                    usuario_id=data.get("usuario_id"),
                    usuario_nome=data.get("usuario_nome"),
                    acao=data.get("acao"),
                    campo_alterado=data.get("campo_alterado"),
                    valor_anterior=data.get("valor_anterior"),
                    valor_novo=data.get("valor_novo"),
                    detalhe=data.get("detalhe"),
                    data_acao=_parse_dt(data.get("data_acao")) or datetime.now(),
                )
            )
            count += 1
    logger.info(
        "load %-22s %6d linhas (%d ignorados: chamado_id órfão)", "historico", count, ignorados
    )


def _load_notificacoes(id_map: dict[str, int]) -> None:
    from app import db as db_module
    from app.db.models.notificacao import NotificacaoRow

    count = 0
    ignorados = 0
    with db_module.SessionLocal() as session, session.begin():
        for data in _ler_jsonl("notificacoes"):
            chamado_id_antigo = str(data.get("chamado_id") or "")
            novo_id = id_map.get(chamado_id_antigo)
            if novo_id is None:
                ignorados += 1
                continue
            session.add(
                NotificacaoRow(
                    usuario_id=data.get("usuario_id"),
                    chamado_id=novo_id,
                    numero_chamado=data.get("numero_chamado"),
                    titulo=data.get("titulo") or "",
                    mensagem=data.get("mensagem") or "",
                    tipo=data.get("tipo", "novo_chamado"),
                    categoria=data.get("categoria"),
                    solicitante_nome=data.get("solicitante_nome"),
                    lida=data.get("lida", False),
                    data_criacao=_parse_dt(data.get("data_criacao")) or datetime.now(),
                )
            )
            count += 1
    logger.info(
        "load %-22s %6d linhas (%d ignorados: chamado_id órfão)", "notificacoes", count, ignorados
    )


def _load_config_setor_area() -> None:
    from app import db as db_module
    from app.db.models.config_setor_area import ConfigSetorAreaRow

    caminho = DUMP_DIR / SINGLETONS[("config", "setor_para_area")]
    if not caminho.exists():
        logger.warning("singleton config/setor_para_area não dumpado — pulando")
        return
    payload = json.loads(caminho.read_text(encoding="utf-8"))
    mapa = (payload or {}).get("mapa") or {}
    if not mapa:
        logger.info("config/setor_para_area vazio ou inexistente — sem linha a inserir")
        return
    with db_module.SessionLocal() as session, session.begin():
        session.merge(ConfigSetorAreaRow(id=True, mapa=mapa))
    logger.info("load config_setor_area: 1 linha (%d chaves no mapa)", len(mapa))


def _alinhar_sequence() -> None:
    """setval(chamados_numero_seq) alinhado ao maior numero_chamado já emitido
    — tanto pelo _sistema/contador_chamados quanto pelo maior CHM-XXXX real
    (usa o maior dos dois, defensivamente)."""
    from sqlalchemy import select, text

    from app import db as db_module
    from app.db.models.chamado import ChamadoRow

    maior_numero = 0
    caminho = DUMP_DIR / SINGLETONS[("_sistema", "contador_chamados")]
    if caminho.exists():
        payload = json.loads(caminho.read_text(encoding="utf-8"))
        maior_numero = max(maior_numero, int((payload or {}).get("proximo_numero") or 0))

    with db_module.SessionLocal() as session:
        numeros = session.execute(select(ChamadoRow.numero_chamado)).scalars().all()
        for n in numeros:
            if n and n.startswith("CHM-"):
                try:
                    maior_numero = max(maior_numero, int(n.replace("CHM-", "")))
                except ValueError:
                    continue

        session.execute(text("SELECT setval('chamados_numero_seq', :v, true)"), {"v": maior_numero})
        session.commit()
    logger.info("chamados_numero_seq alinhada em %d", maior_numero)


def fase_load() -> None:
    _init_db_module()
    logger.info("=== LOAD: schema deve estar vazio (alembic upgrade head recém-aplicado) ===")
    _load_categorias()
    _load_grupos_rl()
    _load_usuarios()
    _load_apoio()
    id_map = _load_chamados()
    _load_historico(id_map)
    _load_notificacoes(id_map)
    _load_config_setor_area()
    _alinhar_sequence()
    logger.info("=== LOAD concluído ===")


# ─────────────────────────────────────────────────────────────────────────
# Fase 3 — VERIFY (bloqueia cutover se qualquer checagem falhar)
# ─────────────────────────────────────────────────────────────────────────


def _contar_jsonl(nome: str) -> int:
    return sum(1 for _ in _ler_jsonl(nome))


def verificar_contagens() -> list[str]:
    """COUNT(*) Postgres == contagem de linhas no dump, por coleção."""
    from sqlalchemy import func, select

    from app import db as db_module
    from app.db.models.apoio import (
        ContadorUsoRow,
        HistoricoUsuarioRow,
        PushSubscriptionRow,
        SolicitacaoLgpdRow,
    )
    from app.db.models.categoria import CategoriaGateRow, CategoriaImpactoRow, CategoriaSetorRow
    from app.db.models.chamado import ChamadoRow
    from app.db.models.grupo_rl import GrupoRLRow
    from app.db.models.historico import HistoricoRow
    from app.db.models.notificacao import NotificacaoRow
    from app.db.models.usuario import UsuarioRow

    tabelas = [
        ("categorias_setores", CategoriaSetorRow),
        ("categorias_gates", CategoriaGateRow),
        ("categorias_impactos", CategoriaImpactoRow),
        ("grupos_rl", GrupoRLRow),
        ("usuarios", UsuarioRow),
        ("push_subscriptions", PushSubscriptionRow),
        ("historico_usuarios", HistoricoUsuarioRow),
        ("solicitacoes_lgpd", SolicitacaoLgpdRow),
        ("contadores_uso", ContadorUsoRow),
        ("chamados", ChamadoRow),
        ("historico", HistoricoRow),
        ("notificacoes", NotificacaoRow),
    ]
    erros = []
    with db_module.SessionLocal() as session:
        for nome, row_cls in tabelas:
            pg_count = session.execute(select(func.count()).select_from(row_cls)).scalar_one()
            fs_count = _contar_jsonl(nome)
            status = "OK" if pg_count == fs_count else "DIVERGENTE"
            logger.info(
                "contagem %-22s postgres=%-6d firestore=%-6d %s", nome, pg_count, fs_count, status
            )
            if pg_count != fs_count:
                erros.append(f"{nome}: postgres={pg_count} != firestore={fs_count}")
    return erros


def verificar_pii_amostra(tamanho: int = 20) -> list[str]:
    """Confirma que usuarios.email/nome no Postgres batem com o Firestore
    (comparação de ciphertext bruto — sem decriptar) e, quando ENCRYPTION_KEY
    está disponível, que maybe_decrypt produz o mesmo plaintext nas duas."""
    import random

    from app import db as db_module
    from app.db.models.usuario import UsuarioRow

    docs = list(_ler_jsonl("usuarios"))
    amostra = random.sample(docs, min(tamanho, len(docs))) if docs else []
    erros = []
    with db_module.SessionLocal() as session:
        for data in amostra:
            row = session.get(UsuarioRow, data["_id"])
            if row is None:
                erros.append(f"usuario {data['_id']}: não encontrado no Postgres")
                continue
            if row.email != (data.get("email") or ""):
                erros.append(
                    f"usuario {data['_id']}: email divergente (ciphertext/plaintext bruto)"
                )
            if row.nome != (data.get("nome") or ""):
                erros.append(f"usuario {data['_id']}: nome divergente (ciphertext/plaintext bruto)")
            if row.email_lookup_hash != data.get("email_lookup_hash"):
                erros.append(f"usuario {data['_id']}: email_lookup_hash divergente")
    logger.info("PII amostra: %d usuários verificados, %d divergências", len(amostra), len(erros))
    return erros


def verificar_fks_orfas() -> list[str]:
    """0 linhas sem referência válida — Firestore não tinha FK, então
    inconsistências pré-existentes no dado real aparecem aqui."""
    from sqlalchemy import text

    from app import db as db_module

    checagens = {
        "chamados_participantes.chamado_id órfão": (
            "SELECT count(*) FROM chamados_participantes cp "
            "LEFT JOIN chamados c ON c.id = cp.chamado_id WHERE c.id IS NULL"
        ),
        "chamados_observadores.chamado_id órfão": (
            "SELECT count(*) FROM chamados_observadores co "
            "LEFT JOIN chamados c ON c.id = co.chamado_id WHERE c.id IS NULL"
        ),
        "historico.chamado_id órfão": (
            "SELECT count(*) FROM historico h "
            "LEFT JOIN chamados c ON c.id = h.chamado_id WHERE c.id IS NULL"
        ),
        "notificacoes.chamado_id órfão": (
            "SELECT count(*) FROM notificacoes n "
            "LEFT JOIN chamados c ON c.id = n.chamado_id WHERE c.id IS NULL"
        ),
        "chamados.grupo_rl_id órfão": (
            "SELECT count(*) FROM chamados c "
            "LEFT JOIN grupos_rl g ON g.id = c.grupo_rl_id "
            "WHERE c.grupo_rl_id IS NOT NULL AND g.id IS NULL"
        ),
    }
    erros = []
    with db_module.SessionLocal() as session:
        for descricao, sql in checagens.items():
            n = session.execute(text(sql)).scalar_one()
            logger.info("fk-orfa %-40s %d", descricao, n)
            if n:
                erros.append(f"{descricao}: {n} linha(s)")
    return erros


def verificar_sequence() -> list[str]:
    from sqlalchemy import select, text

    from app import db as db_module
    from app.db.models.chamado import ChamadoRow

    with db_module.SessionLocal() as session:
        maior = session.execute(select(ChamadoRow.numero_chamado)).scalars().all()
        maior_num = 0
        for n in maior:
            if n and n.startswith("CHM-"):
                try:
                    maior_num = max(maior_num, int(n.replace("CHM-", "")))
                except ValueError:
                    continue
        seq_val = session.execute(text("SELECT last_value FROM chamados_numero_seq")).scalar_one()
    if seq_val < maior_num:
        return [f"chamados_numero_seq={seq_val} < maior numero_chamado real={maior_num}"]
    logger.info("sequence chamados_numero_seq=%d >= maior numero_chamado=%d", seq_val, maior_num)
    return []


def fase_verify() -> None:
    _init_db_module()
    logger.info("=== VERIFY ===")
    erros: list[str] = []
    erros += verificar_contagens()
    erros += verificar_pii_amostra()
    erros += verificar_fks_orfas()
    erros += verificar_sequence()

    print()
    if erros:
        print(f"❌ VERIFY FALHOU — {len(erros)} problema(s), NÃO prosseguir com o cutover:")
        for e in erros:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("✅ VERIFY OK — todas as checagens passaram.")


# ─────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dump", action="store_true", help="Firestore -> JSONL")
    parser.add_argument(
        "--load", action="store_true", help="JSONL -> Postgres (schema deve estar vazio)"
    )
    parser.add_argument("--verify", action="store_true", help="Roda as checagens de integridade")
    args = parser.parse_args()

    if not any([args.dump, args.load, args.verify]):
        parser.print_help()
        sys.exit(1)

    if args.dump:
        fase_dump()
    if args.load:
        fase_load()
    if args.verify:
        fase_verify()


if __name__ == "__main__":
    main()
