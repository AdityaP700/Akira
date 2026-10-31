import os
from logging.config import fileConfig

os.environ["ALEMBIC_MIGRATION_RUNNING"] = "1"

import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool

import app.repositories.models  # noqa: F401
from alembic import context
from app.core.config import settings
from app.core.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _normalize_db_url(url: str) -> str:
    """Normalize legacy postgres:// or standard postgresql:// to postgresql+psycopg://."""
    if not url:
        return url
    trimmed = url.strip()
    if trimmed.startswith("postgres://"):
        return "postgresql+psycopg://" + trimmed[len("postgres://") :]
    if trimmed.startswith("postgresql://"):
        return "postgresql+psycopg://" + trimmed[len("postgresql://") :]
    return trimmed


def run_migrations_offline() -> None:
    url = _normalize_db_url(
        config.get_main_option("sqlalchemy.url")
        or settings.MIGRATION_DATABASE_URL
        or settings.DATABASE_URL
    )
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    url = _normalize_db_url(
        config.get_main_option("sqlalchemy.url")
        or settings.MIGRATION_DATABASE_URL
        or settings.DATABASE_URL
    )
    if not url:
        raise ValueError(
            "Alembic requires a database URL. Please set MIGRATION_DATABASE_URL or DATABASE_URL."
        )
    configuration["sqlalchemy.url"] = url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        if connection.dialect.name == "postgresql":
            try:
                connection.execute(
                    sa.text(
                        "CREATE TABLE IF NOT EXISTS alembic_version ("
                        "version_num VARCHAR(128) NOT NULL, "
                        "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)"
                        ");"
                    )
                )
                connection.execute(
                    sa.text(
                        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128);"
                    )
                )
                connection.commit()
            except Exception:
                connection.rollback()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
