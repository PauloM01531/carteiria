"""Isolamento entre usuários A e B — pela API e diretamente no banco (RLS)."""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.db import get_app_engine
from tests.conftest import PASSWORD, UserClient, owner_exec

API = "/api/v1"


def uid(email: str) -> uuid.UUID:
    return owner_exec("SELECT id FROM users WHERE email=:e", e=email).scalar()


# ---------------- Pela API ----------------

def test_preferencias_sao_isoladas(user_a, user_b):
    assert user_a.put(f"{API}/me/preferences", json={"theme": "dark"}).json()["theme"] == "dark"
    assert user_b.put(f"{API}/me/preferences", json={"theme": "light"}).json()["theme"] == "light"
    assert user_a.get(f"{API}/me/preferences").json()["theme"] == "dark"
    assert user_b.get(f"{API}/me/preferences").json()["theme"] == "light"


def test_nao_e_possivel_falsificar_identidade_no_corpo(user_a, user_b):
    b_id = str(uid("bruno@exemplo.com.br"))
    r = user_a.put(f"{API}/me/preferences", json={"theme": "dark", "user_id": b_id})
    assert r.status_code == 422
    r = user_a.patch(f"{API}/me", json={"display_name": "X", "id": b_id})
    assert r.status_code == 422
    r = user_a.patch(f"{API}/me", json={"display_name": "Novo nome", "role": "ADMIN"})
    assert r.status_code == 422
    assert user_b.get(f"{API}/me").json()["display_name"] == "Bruno Teste"
    assert user_a.get(f"{API}/me").json()["role"] == "USER"


def test_a_nao_ve_nem_encerra_sessoes_de_b(user_a, user_b):
    a_sessions = user_a.get(f"{API}/me/sessions").json()
    b_sessions = user_b.get(f"{API}/me/sessions").json()
    assert {s["id"] for s in a_sessions}.isdisjoint({s["id"] for s in b_sessions})

    # Trocar o ID na URL não dá acesso à sessão de B
    r = user_a.delete(f"{API}/me/sessions/{b_sessions[0]['id']}")
    assert r.status_code == 404
    assert user_b.get(f"{API}/me").status_code == 200
    # ID aleatório e ID malformado
    assert user_a.delete(f"{API}/me/sessions/{uuid.uuid4()}").status_code == 404
    assert user_a.delete(f"{API}/me/sessions/1%20OR%201=1").status_code == 422


def test_cookie_de_a_identifica_somente_a(user_a, user_b):
    assert user_a.get(f"{API}/me").json()["email"] == "ana@exemplo.com.br"
    assert user_b.get(f"{API}/me").json()["email"] == "bruno@exemplo.com.br"
    # CSRF de A não serve para a sessão de B
    r = user_b.http.patch(f"{API}/me", json={"display_name": "X"}, headers={"X-CSRF-Token": user_a.csrf})
    assert r.status_code == 403


# ---------------- Diretamente no banco (papel da aplicação + RLS) ----------------

def _as_app(user_id, sql: str, **params):
    with get_app_engine().begin() as conn:
        conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user_id) if user_id else ""})
        return conn.execute(text(sql), params)


def test_rls_select_retorna_somente_linhas_do_usuario(user_a, user_b):
    user_a.put(f"{API}/me/preferences", json={"theme": "dark"})
    user_b.put(f"{API}/me/preferences", json={"theme": "light"})
    a, b = uid("ana@exemplo.com.br"), uid("bruno@exemplo.com.br")

    rows = _as_app(a, "SELECT user_id FROM user_preferences").all()
    assert [r[0] for r in rows] == [a]
    rows = _as_app(b, "SELECT user_id FROM user_preferences").all()
    assert [r[0] for r in rows] == [b]
    # Sem usuário definido: nada é retornado (negação por padrão)
    assert _as_app(None, "SELECT * FROM user_preferences").all() == []
    # Mesmo filtrando explicitamente pelo id de B, A não enxerga
    assert _as_app(a, "SELECT * FROM user_preferences WHERE user_id=:b", b=b).all() == []


def test_rls_update_e_delete_nao_afetam_outro_usuario(user_a, user_b):
    user_b.put(f"{API}/me/preferences", json={"theme": "light"})
    a, b = uid("ana@exemplo.com.br"), uid("bruno@exemplo.com.br")
    assert _as_app(a, "UPDATE user_preferences SET theme='dark' WHERE user_id=:b", b=b).rowcount == 0
    assert _as_app(a, "DELETE FROM user_preferences WHERE user_id=:b", b=b).rowcount == 0
    assert _as_app(b, "SELECT theme FROM user_preferences").scalar() == "light"


def test_rls_insert_em_nome_de_outro_usuario_e_bloqueado(user_a, user_b):
    a, b = uid("ana@exemplo.com.br"), uid("bruno@exemplo.com.br")
    with pytest.raises(DBAPIError, match="row-level security"):
        _as_app(a, "INSERT INTO user_preferences (user_id, theme) VALUES (:b, 'dark')", b=b)


def test_rls_update_nao_pode_transferir_linha_para_outro_usuario(user_a, user_b):
    user_a.put(f"{API}/me/preferences", json={"theme": "dark"})
    a, b = uid("ana@exemplo.com.br"), uid("bruno@exemplo.com.br")
    with pytest.raises(DBAPIError, match="row-level security"):
        _as_app(a, "UPDATE user_preferences SET user_id=:b WHERE user_id=:a", a=a, b=b)


def test_rls_forcado_vale_ate_para_o_dono_das_tabelas(user_a):
    user_a.put(f"{API}/me/preferences", json={"theme": "dark"})
    # FORCE ROW LEVEL SECURITY: nem o papel dono enxerga linhas sem app.user_id definido
    assert owner_exec("SELECT count(*) FROM user_preferences").scalar() == 0
    assert _as_app(uid("ana@exemplo.com.br"), "SELECT count(*) FROM user_preferences").scalar() == 1


def test_papel_da_aplicacao_tem_privilegios_minimos(user_a):
    with get_app_engine().connect() as conn:
        row = conn.execute(text(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
        assert row == (False, False)
    a = uid("ana@exemplo.com.br")
    # Não consegue se promover a ADMIN nem com SQL direto
    with pytest.raises(ProgrammingError, match="permission denied"):
        _as_app(a, "UPDATE users SET role='ADMIN' WHERE id=:a", a=a)
    # Não consegue alterar nem apagar a auditoria
    with pytest.raises(ProgrammingError, match="permission denied"):
        _as_app(a, "UPDATE audit_logs SET result='x'")
    with pytest.raises(ProgrammingError, match="permission denied"):
        _as_app(a, "DELETE FROM audit_logs")
    # Não consegue desativar o RLS
    with pytest.raises(ProgrammingError, match="must be owner"):
        _as_app(a, "ALTER TABLE user_preferences DISABLE ROW LEVEL SECURITY")


# ---------------- Exclusão de conta ----------------

def test_exclusao_de_conta_remove_somente_os_dados_do_titular(user_a, user_b):
    user_a.put(f"{API}/me/preferences", json={"theme": "dark"})
    user_b.put(f"{API}/me/preferences", json={"theme": "light"})
    a, b = uid("ana@exemplo.com.br"), uid("bruno@exemplo.com.br")

    # Exige senha e confirmação explícita
    assert user_a.delete(f"{API}/me", json={"password": "errada12345", "confirmation": "EXCLUIR"}).status_code == 400
    assert user_a.delete(f"{API}/me", json={"password": PASSWORD, "confirmation": "sim"}).status_code == 422

    r = user_a.delete(f"{API}/me", json={"password": PASSWORD, "confirmation": "EXCLUIR"})
    assert r.status_code == 200
    assert owner_exec("SELECT count(*) FROM users WHERE id=:a", a=a).scalar() == 0
    assert _as_app(a, "SELECT count(*) FROM user_preferences").scalar() == 0
    assert owner_exec("SELECT count(*) FROM user_sessions WHERE user_id=:a", a=a).scalar() == 0
    # B continua intacto
    assert _as_app(b, "SELECT theme FROM user_preferences").scalar() == "light"
    assert user_b.get(f"{API}/me").status_code == 200
    # A não consegue mais entrar e a sessão antiga não vale
    assert user_a.get(f"{API}/me").status_code == 401
    assert UserClient().login("ana@exemplo.com.br").status_code == 401
    # Auditoria guarda só o id, sem e-mail
    log = owner_exec("SELECT actor_email FROM audit_logs WHERE action='account_deleted'").one()
    assert log[0] is None
