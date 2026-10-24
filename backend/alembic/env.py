"""Migrações rodam com o papel DONO das tabelas (nunca com o papel da aplicação)."""
from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.models import Base

target_metadata = Base.metadata


def run_migrations_online() -> None:
    engine = create_engine(get_settings().owner_database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("Modo offline não suportado.")
run_migrations_online()
