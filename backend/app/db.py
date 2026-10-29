"""Conexões com o banco.

A API usa SOMENTE o papel `DB_APP_USER`, que não é dono das tabelas e não tem
BYPASSRLS. Em cada transação, o id do usuário autenticado é gravado em
`app.user_id` (escopo da transação) e as políticas de Row-Level Security usam
esse valor. Sem usuário definido, as tabelas privadas não retornam nada.

O papel dono (`DB_OWNER_USER`) é usado apenas por migrações e pela CLI
administrativa executada no servidor.
"""
from collections.abc import Iterator
from uuid import UUID

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_engines: dict[str, Engine] = {}

RLS_KEY = "rls_user_id"


def get_app_engine() -> Engine:
    if "app" not in _engines:
        # hide_parameters: erros do banco não levam valores (hash de senha, descrições) para os logs.
        _engines["app"] = create_engine(
            get_settings().app_database_url, pool_pre_ping=True, pool_size=10, hide_parameters=True
        )
    return _engines["app"]


def get_owner_engine() -> Engine:
    if "owner" not in _engines:
        _engines["owner"] = create_engine(get_settings().owner_database_url, pool_pre_ping=True, hide_parameters=True)
    return _engines["owner"]


def reset_engines() -> None:
    for eng in _engines.values():
        eng.dispose()
    _engines.clear()


@event.listens_for(Session, "after_begin")
def _apply_rls_user(session: Session, transaction, connection) -> None:  # noqa: ANN001
    """Reaplica o usuário do RLS no início de toda transação desta sessão."""
    uid = session.info.get(RLS_KEY)
    connection.exec_driver_sql(
        "SELECT set_config('app.user_id', %s, true)", (str(uid) if uid else "",)
    )


def set_rls_user(db: Session, user_id: UUID | None) -> None:
    """Define (ou limpa) o usuário cujas linhas privadas esta sessão pode acessar."""
    db.info[RLS_KEY] = user_id
    db.execute(
        text("SELECT set_config('app.user_id', :uid, true)"),
        {"uid": str(user_id) if user_id else ""},
    )


def get_db() -> Iterator[Session]:
    factory = sessionmaker(bind=get_app_engine(), expire_on_commit=False)
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
