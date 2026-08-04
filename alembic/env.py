import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

# Modelos precisam estar importados pra popular Base.metadata antes do
# autogenerate — app/db/models/__init__.py importa cada model novo conforme
# cada marco introduz uma tabela.
import app.db.models  # noqa: E402, F401
from alembic import context
from app.db import normalizar_url_driver  # noqa: E402
from app.db.base import Base  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# URL nunca vem hardcoded do alembic.ini: DATABASE_URL (produção) ou
# TEST_DATABASE_URL (CI/dev local, ver docs/ENV.md) — mesmo padrão de
# config.py. Prioriza TEST_DATABASE_URL quando setada, pra não arriscar
# rodar migration de teste contra produção por engano.
_db_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
if _db_url:
    config.set_main_option("sqlalchemy.url", normalizar_url_driver(_db_url))

# Interpret the config file for Python logging.
# disable_existing_loggers=False: o padrão (True) desliga TODOS os loggers já
# configurados fora do alembic.ini — inclusive os da app (ex. "app.metrics"),
# o que quebra caplog em qualquer teste que rode depois da migration numa
# mesma sessão de pytest (db_engine é session-scoped, roda uma vez só).
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
