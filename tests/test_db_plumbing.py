"""Smoke tests da plumbing Postgres (Fase 2 — Marco 2: app/db/ + Alembic).

Valida que db_engine/db_session (tests/conftest.py) funcionam de ponta a ponta
contra um Postgres real, antes de qualquer model ser migrado (Marco 3+).
"""

from sqlalchemy import text

import app.db


def test_db_session_executa_query_real(db_session):
    """db_session conecta a um Postgres real e executa uma query simples."""
    resultado = db_session.execute(text("SELECT 1")).scalar_one()
    assert resultado == 1


def test_db_session_substitui_session_local(db_session):
    """A fixture monkeypatcha app.db.SessionLocal pra apontar pra sessão de teste."""
    assert app.db.SessionLocal is not None
    session_da_producao = app.db.SessionLocal()
    resultado = session_da_producao.execute(text("SELECT 1")).scalar_one()
    assert resultado == 1


def test_db_session_isola_mudancas_entre_testes_a(db_session):
    """Cria uma tabela temporária + linha; não deve sobreviver ao próximo teste."""
    db_session.execute(text("CREATE TABLE IF NOT EXISTS _smoke_test (id INTEGER)"))
    db_session.execute(text("INSERT INTO _smoke_test (id) VALUES (1)"))
    db_session.flush()
    count = db_session.execute(text("SELECT COUNT(*) FROM _smoke_test")).scalar_one()
    assert count == 1


def test_db_session_isola_mudancas_entre_testes_b(db_session):
    """Confirma que o rollback do teste anterior realmente aconteceu."""
    existe = db_session.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = '_smoke_test')"
        )
    ).scalar_one()
    assert existe is False
