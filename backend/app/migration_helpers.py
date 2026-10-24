"""SQL reutilizado pelas migrações para proteger tabelas privadas.

Atenção: migrações antigas importam estas funções. Não altere o comportamento;
crie novas funções se precisar de regras diferentes.
"""
import os


def app_role() -> str:
    role = os.environ.get("DB_APP_USER") or _from_settings()
    if not role.replace("_", "").isalnum():
        raise ValueError("Nome de papel inválido")
    return role


def _from_settings() -> str:
    from app.config import get_settings

    return get_settings().db_app_user


def private_table_sql(table: str, owner_column: str = "user_id") -> list[str]:
    """RLS forçado + políticas por operação, comparando com app.user_id da transação."""
    role = app_role()
    cond = f"{owner_column} = NULLIF(current_setting('app.user_id', true), '')::uuid"
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {role}",
        f"CREATE POLICY {table}_select ON {table} FOR SELECT TO {role} USING ({cond})",
        f"CREATE POLICY {table}_insert ON {table} FOR INSERT TO {role} WITH CHECK ({cond})",
        f"CREATE POLICY {table}_update ON {table} FOR UPDATE TO {role} USING ({cond}) WITH CHECK ({cond})",
        f"CREATE POLICY {table}_delete ON {table} FOR DELETE TO {role} USING ({cond})",
    ]
