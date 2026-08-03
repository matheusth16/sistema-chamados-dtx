"""Testes para contadores_uso.py — limites diários por usuário (Fase 2 —
Postgres real). O incremento condicional agora é uma única query atômica
(INSERT ... ON CONFLICT DO UPDATE ... WHERE ... RETURNING), sem transação
Firestore explícita — o teste de concorrência prova que o limite é
respeitado mesmo com requests simultâneos reais."""

import threading

import pytest

pytestmark = pytest.mark.usefixtures("db_session")


# ── verificar_e_incrementar_relatorio ─────────────────────────────────────────


def test_relatorio_limite_zero_retorna_true_sem_tocar_banco(app):
    from app.services.contadores_uso import verificar_e_incrementar_relatorio

    ok, err = verificar_e_incrementar_relatorio("user1", 0)
    assert ok is True
    assert err is None


def test_relatorio_user_id_vazio_retorna_true(app):
    from app.services.contadores_uso import verificar_e_incrementar_relatorio

    ok, err = verificar_e_incrementar_relatorio("", 10)
    assert ok is True
    assert err is None


def test_relatorio_primeira_chamada_cria_e_retorna_true(app):
    from app.services.contadores_uso import verificar_e_incrementar_relatorio

    ok, err = verificar_e_incrementar_relatorio("user1", 5)
    assert ok is True
    assert err is None


def test_relatorio_abaixo_do_limite_incrementa(app):
    from app.services.contadores_uso import verificar_e_incrementar_relatorio

    for _ in range(4):
        ok, err = verificar_e_incrementar_relatorio("user1", 5)
        assert ok is True
        assert err is None


def test_relatorio_limite_atingido_retorna_false(app):
    from app.services.contadores_uso import verificar_e_incrementar_relatorio

    for _ in range(5):
        ok, _ = verificar_e_incrementar_relatorio("user1", 5)
        assert ok is True

    ok, err = verificar_e_incrementar_relatorio("user1", 5)
    assert ok is False
    assert err is not None
    assert "limit" in err.lower() or "limite" in err.lower()


def test_relatorio_excecao_no_banco_retorna_true_fail_open(app, monkeypatch):
    from app.services import contadores_uso

    def _explode():
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(contadores_uso.db_module, "SessionLocal", _explode)

    ok, err = contadores_uso.verificar_e_incrementar_relatorio("user1", 5)
    assert ok is True
    assert err is None


# ── verificar_e_incrementar_export ────────────────────────────────────────────


def test_export_limite_zero_retorna_true(app):
    from app.services.contadores_uso import verificar_e_incrementar_export

    ok, err = verificar_e_incrementar_export("user2", 0)
    assert ok is True
    assert err is None


def test_export_primeira_chamada_cria_e_retorna_true(app):
    from app.services.contadores_uso import verificar_e_incrementar_export

    ok, err = verificar_e_incrementar_export("user2", 3)
    assert ok is True
    assert err is None


def test_export_limite_atingido_retorna_false(app):
    from app.services.contadores_uso import verificar_e_incrementar_export

    for _ in range(3):
        ok, _ = verificar_e_incrementar_export("user2", 3)
        assert ok is True

    ok, err = verificar_e_incrementar_export("user2", 3)
    assert ok is False
    assert err is not None


def test_relatorio_e_export_sao_contadores_independentes(app):
    """Incrementar relatorio não afeta o limite de export pro mesmo usuário/dia."""
    from app.services.contadores_uso import (
        verificar_e_incrementar_export,
        verificar_e_incrementar_relatorio,
    )

    for _ in range(3):
        verificar_e_incrementar_relatorio("user3", 3)

    ok, err = verificar_e_incrementar_export("user3", 3)
    assert ok is True
    assert err is None


# ── Concorrência real ─────────────────────────────────────────────────────────


def test_relatorio_concorrencia_real_nao_ultrapassa_limite(db_engine, monkeypatch):
    """20 threads (conexões físicas separadas) disputando um limite de 5 —
    exatamente 5 devem ser permitidas, provando que o WHERE do ON CONFLICT
    é avaliado atomicamente pelo Postgres, sem race condition."""
    from sqlalchemy.orm import scoped_session, sessionmaker

    from app.services import contadores_uso

    real_factory = scoped_session(
        sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    )
    monkeypatch.setattr(contadores_uso.db_module, "SessionLocal", real_factory)

    resultados = []

    def _tentar():
        try:
            ok, _ = contadores_uso.verificar_e_incrementar_relatorio("user_concorrente", 5)
            resultados.append(ok)
        finally:
            real_factory.remove()

    threads = [threading.Thread(target=_tentar) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    from sqlalchemy import text

    with db_engine.connect() as conn:
        conn.execute(text("DELETE FROM contadores_uso WHERE user_id = 'user_concorrente'"))
        conn.commit()

    assert sum(1 for r in resultados if r) == 5
    assert sum(1 for r in resultados if not r) == 15


# ── limpar_contadores_antigos ─────────────────────────────────────────────────


def _inserir_contador_antigo(user_id, dias_atras=100, relatorio=1, export=0):
    """Insere um registro via a sessão isolada do teste (savepoint) — não
    através de db_engine diretamente, senão o commit seria real e sobreviveria
    entre execuções da suíte."""
    from datetime import UTC, datetime, timedelta

    from app.db.models.apoio import ContadorUsoRow
    from app.services import contadores_uso

    data_antiga = (datetime.now(UTC) - timedelta(days=dias_atras)).date()
    with contadores_uso.db_module.SessionLocal() as session, session.begin():
        session.add(
            ContadorUsoRow(
                user_id=user_id,
                data=data_antiga,
                relatorio_geracoes=relatorio,
                export_excel_geracoes=export,
            )
        )


def test_limpar_contadores_dry_run_nao_deleta(app):
    from app.services.contadores_uso import limpar_contadores_antigos

    _inserir_contador_antigo("user_antigo")

    resultado = limpar_contadores_antigos(dias=90, dry_run=True)

    assert resultado["dry_run"] is True
    assert resultado["removidos"] >= 1
    assert resultado["erros"] == 0


def test_limpar_contadores_apply_deleta_antigos(app):
    from sqlalchemy import select

    from app.db.models.apoio import ContadorUsoRow
    from app.services import contadores_uso
    from app.services.contadores_uso import limpar_contadores_antigos

    _inserir_contador_antigo("user_antigo2")

    resultado = limpar_contadores_antigos(dias=90, dry_run=False)

    assert resultado["dry_run"] is False
    assert resultado["removidos"] >= 1

    with contadores_uso.db_module.SessionLocal() as session:
        restante = session.execute(
            select(ContadorUsoRow).where(ContadorUsoRow.user_id == "user_antigo2")
        ).first()
    assert restante is None


def test_limpar_contadores_nao_remove_recentes(app):
    from app.services.contadores_uso import (
        limpar_contadores_antigos,
        verificar_e_incrementar_relatorio,
    )

    verificar_e_incrementar_relatorio("user_recente", 10)

    resultado = limpar_contadores_antigos(dias=90, dry_run=False)

    from sqlalchemy import select

    from app.db.models.apoio import ContadorUsoRow
    from app.services import contadores_uso

    with contadores_uso.db_module.SessionLocal() as session:
        ainda_existe = session.execute(
            select(ContadorUsoRow).where(ContadorUsoRow.user_id == "user_recente")
        ).first()
    assert ainda_existe is not None
    assert resultado["erros"] == 0
