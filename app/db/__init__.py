"""
Camada de acesso a dado PostgreSQL (Fase 2 — substitui app/database.py/Firestore).

Padrão de inicialização manual explícita, sem Flask-SQLAlchemy — mesmo estilo já
usado em app/database.py (init do Firebase Admin com retry manual).
"""

import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from app.db.base import Base

logger = logging.getLogger(__name__)

engine = None
SessionLocal: scoped_session | None = None


def normalizar_url_driver(url: str) -> str:
    """Força o driver psycopg (v3, `requirements.txt`) em URLs `postgresql://` puras.

    Sem `+psycopg`, o SQLAlchemy tenta psycopg2 por padrão — não instalado neste
    projeto (`psycopg[binary]==3.3.4`, não `psycopg2`). `.env`/`.env.example`/
    `ci.yml` guardam a URL sem driver por legibilidade; esta função é o único
    lugar que precisa saber do detalhe do driver.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def init_engine(app):
    """Cria o engine e a sessão a partir de app.config['DATABASE_URL'].

    Chamado em create_app(). app.teardown_appcontext deve remover a sessão
    (SessionLocal.remove()) ao final de cada request.
    """
    global engine, SessionLocal

    database_url = app.config.get("DATABASE_URL")
    if not database_url:
        logger.warning("DATABASE_URL não configurada — app/db não inicializado.")
        return

    engine = create_engine(normalizar_url_driver(database_url), pool_pre_ping=True)
    SessionLocal = scoped_session(
        sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    )

    @app.teardown_appcontext
    def _remove_session(exception=None):
        if SessionLocal is not None:
            SessionLocal.remove()


__all__ = ["Base", "SessionLocal", "engine", "init_engine"]
