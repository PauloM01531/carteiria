"""Infraestrutura de testes.

Os testes usam um banco PostgreSQL real e separado (DB_TEST_NAME), com as mesmas
migrações, papéis e políticas RLS de produção. Nenhum dado real é usado.
"""
import os
import re
from collections.abc import Iterator

os.environ["DB_NAME_OVERRIDE"] = os.environ.get("DB_TEST_NAME", "carteiria_test")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_owner_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security.rate_limit import limiter  # noqa: E402
from app.services.email import MemoryEmailSender, set_email_sender  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORD = "SenhaForte123"

_super_engine = None


def super_engine():
    """Superusuário do banco de TESTES: só para preparar/limpar dados (ignora RLS)."""
    global _super_engine
    if _super_engine is None:
        from sqlalchemy import create_engine
        s = get_settings()
        url = s.owner_database_url.replace(
            f"{s.db_owner_user}:", "postgres:", 1).replace(
            s.db_owner_password, s.postgres_superuser_password or "", 1)
        _super_engine = create_engine(url)
    return _super_engine


@pytest.fixture(scope="session", autouse=True)
def migrated_db() -> None:
    assert get_settings().db_name_override, "testes devem usar o banco de testes"
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def clean_state() -> Iterator[None]:
    with super_engine().begin() as conn:
        # DELETE (e não TRUNCATE) para preservar as categorias padrão do sistema.
        conn.execute(text("DELETE FROM transactions"))
        conn.execute(text("DELETE FROM categories WHERE user_id IS NOT NULL"))
        conn.execute(text("DELETE FROM users"))
        conn.execute(text("DELETE FROM invites"))
        conn.execute(text("DELETE FROM audit_logs"))
        conn.execute(text("""UPDATE app_settings SET value = '"approval"' WHERE key = 'registration_mode'"""))
    limiter.reset()
    yield


@pytest.fixture
def mailbox() -> MemoryEmailSender:
    sender = MemoryEmailSender()
    set_email_sender(sender)
    return sender


def super_exec(sql: str, **params):
    with super_engine().begin() as conn:
        return conn.execute(text(sql), params)


def owner_exec(sql: str, **params):
    with get_owner_engine().begin() as conn:
        return conn.execute(text(sql), params)


def extract_token(body: str, marker: str) -> str:
    m = re.search(re.escape(marker) + r"=([A-Za-z0-9_\-]+)", body)
    assert m, f"token '{marker}' não encontrado no e-mail"
    return m.group(1)


class UserClient:
    """Um navegador independente (cookies próprios) para um usuário."""

    def __init__(self) -> None:
        self.http = TestClient(app)
        self.csrf: str | None = None
        self.user: dict | None = None

    def _headers(self, extra: dict | None = None) -> dict:
        h = dict(extra or {})
        if self.csrf:
            h.setdefault("X-CSRF-Token", self.csrf)
        return h

    def get(self, url: str, **kw):
        return self.http.get(url, **kw)

    def post(self, url: str, headers: dict | None = None, **kw):
        return self.http.post(url, headers=self._headers(headers), **kw)

    def put(self, url: str, headers: dict | None = None, **kw):
        return self.http.put(url, headers=self._headers(headers), **kw)

    def patch(self, url: str, headers: dict | None = None, **kw):
        return self.http.patch(url, headers=self._headers(headers), **kw)

    def delete(self, url: str, headers: dict | None = None, **kw):
        return self.http.request("DELETE", url, headers=self._headers(headers), **kw)

    def login(self, email: str, password: str = PASSWORD):
        r = self.http.post("/api/v1/auth/login", json={"email": email, "password": password})
        if r.status_code == 200:
            self.csrf = r.json()["csrf_token"]
            self.user = r.json()["user"]
        return r


def register_and_verify(mailbox: MemoryEmailSender, email: str, name: str, password: str = PASSWORD,
                        invite_token: str | None = None) -> None:
    c = TestClient(app)
    body = {"display_name": name, "email": email, "password": password}
    if invite_token:
        body["invite_token"] = invite_token
    r = c.post("/api/v1/auth/register", json=body)
    assert r.status_code == 202, r.text
    mail = [m for m in mailbox.outbox if m.to == email and "Confirme" in m.subject][-1]
    token = extract_token(mail.body, "#token")
    r = c.post("/api/v1/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text


def make_user(mailbox: MemoryEmailSender, email: str, name: str, role: str = "USER") -> UserClient:
    register_and_verify(mailbox, email, name)
    # Aprovação/promoção feita como o procedimento seguro do servidor (papel dono).
    owner_exec("UPDATE users SET status='active', role=:role WHERE email=:e", role=role, e=email)
    client = UserClient()
    r = client.login(email)
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def user_a(mailbox) -> UserClient:
    return make_user(mailbox, "ana@exemplo.com.br", "Ana Teste")


@pytest.fixture
def user_b(mailbox) -> UserClient:
    return make_user(mailbox, "bruno@exemplo.com.br", "Bruno Teste")


@pytest.fixture
def admin(mailbox) -> UserClient:
    return make_user(mailbox, "admin@exemplo.com.br", "Admin Teste", role="ADMIN")
