"""Painel administrativo: papéis ADMIN x USER, aprovação, convites e auditoria."""
import uuid

from fastapi.testclient import TestClient

from app import cli
from app.main import app
from tests.conftest import PASSWORD, UserClient, enable_mfa, owner_exec, register_and_verify

API = "/api/v1"

ADMIN_ENDPOINTS = [
    ("GET", "/admin/users"),
    ("GET", "/admin/stats"),
    ("GET", "/admin/registration-mode"),
    ("PUT", "/admin/registration-mode"),
    ("GET", "/admin/invites"),
    ("POST", "/admin/invites"),
    ("DELETE", f"/admin/invites/{uuid.uuid4()}"),
    ("POST", f"/admin/users/{uuid.uuid4()}/approve"),
    ("POST", f"/admin/users/{uuid.uuid4()}/reject"),
    ("POST", f"/admin/users/{uuid.uuid4()}/suspend"),
    ("POST", f"/admin/users/{uuid.uuid4()}/reactivate"),
    ("GET", "/admin/audit-logs"),
]

BODIES = {"/admin/registration-mode": {"mode": "approval"}, "/admin/invites": {"email": "x@exemplo.com.br"}}


def _call(client: UserClient, method: str, path: str):
    body = BODIES.get(path)
    fn = {"GET": client.get, "POST": client.post, "PUT": client.put, "DELETE": client.delete}[method]
    return fn(API + path, json=body) if body is not None and method != "GET" else fn(API + path)


def test_usuario_comum_nao_acessa_nenhum_endpoint_admin(user_a):
    for method, path in ADMIN_ENDPOINTS:
        r = _call(user_a, method, path)
        assert r.status_code == 403, (method, path, r.status_code)
    denied = owner_exec("SELECT count(*) FROM audit_logs WHERE action='admin_access_denied'").scalar()
    assert denied == len(ADMIN_ENDPOINTS)
    # Nada mudou
    assert owner_exec("SELECT value FROM app_settings WHERE key='registration_mode'").scalar() == "approval"
    assert owner_exec("SELECT count(*) FROM invites").scalar() == 0


def test_sem_login_endpoints_admin_retornam_401():
    c = TestClient(app)
    for method, path in ADMIN_ENDPOINTS:
        r = c.request(method, API + path, json=BODIES.get(path) if method != "GET" else None)
        assert r.status_code == 401, (method, path)


def test_usuario_nao_consegue_aprovar_a_si_mesmo_nem_outro(mailbox, user_a):
    register_and_verify(mailbox, "pendente@exemplo.com.br", "Pendente")
    pid = owner_exec("SELECT id FROM users WHERE email='pendente@exemplo.com.br'").scalar()
    assert user_a.post(f"{API}/admin/users/{pid}/approve").status_code == 403
    assert owner_exec("SELECT status FROM users WHERE id=:p", p=pid).scalar() == "pending_approval"


def test_admin_aprova_e_rejeita_cadastros(mailbox, admin):
    register_and_verify(mailbox, "p1@exemplo.com.br", "P Um")
    register_and_verify(mailbox, "p2@exemplo.com.br", "P Dois")
    pending = admin.get(f"{API}/admin/users", params={"status": "pending_approval"}).json()
    ids = {u["email"]: u["id"] for u in pending}
    assert set(ids) == {"p1@exemplo.com.br", "p2@exemplo.com.br"}

    assert admin.post(f"{API}/admin/users/{ids['p1@exemplo.com.br']}/approve").json()["status"] == "active"
    assert admin.post(f"{API}/admin/users/{ids['p2@exemplo.com.br']}/reject").json()["status"] == "rejected"
    assert UserClient().login("p1@exemplo.com.br").status_code == 200
    r = UserClient().login("p2@exemplo.com.br")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "rejected"
    # Aprovar de novo uma conta ativa é recusado
    assert admin.post(f"{API}/admin/users/{ids['p1@exemplo.com.br']}/approve").status_code == 409


def test_admin_suspende_e_reativa_revogando_sessoes(admin, user_b):
    b_id = owner_exec("SELECT id FROM users WHERE email='bruno@exemplo.com.br'").scalar()
    assert admin.post(f"{API}/admin/users/{b_id}/suspend").status_code == 200
    assert user_b.get(f"{API}/me").status_code == 401  # sessão revogada na hora
    assert owner_exec(
        "SELECT count(*) FROM user_sessions WHERE user_id=:b AND revoked_at IS NULL", b=b_id).scalar() == 0
    assert admin.post(f"{API}/admin/users/{b_id}/reactivate").status_code == 200
    assert UserClient().login("bruno@exemplo.com.br").status_code == 200


def test_admin_nao_age_sobre_si_ou_outro_admin(admin):
    me = admin.user["id"]
    assert admin.post(f"{API}/admin/users/{me}/suspend").status_code == 400


def test_lista_de_usuarios_nao_expoe_dados_sensiveis(admin, user_a):
    users = admin.get(f"{API}/admin/users", params={"q": "ana"}).json()
    assert len(users) == 1 and users[0]["email"] == "ana@exemplo.com.br"
    assert set(users[0]) == {"id", "email", "display_name", "role", "status", "email_verified",
                             "created_at", "last_login_at"}
    assert "argon2" not in admin.get(f"{API}/admin/users").text


def test_admin_nao_ve_preferencias_de_outros_usuarios(admin, user_a):
    user_a.put(f"{API}/me/preferences", json={"theme": "dark"})
    # O admin só enxerga as próprias preferências; não existe rota para dados de outros.
    assert admin.get(f"{API}/me/preferences").json()["theme"] == "system"


def test_modo_de_cadastro_e_auditoria(admin):
    assert admin.get(f"{API}/admin/registration-mode").json()["mode"] == "approval"
    assert admin.put(f"{API}/admin/registration-mode", json={"mode": "invite"}).json()["mode"] == "invite"
    assert admin.put(f"{API}/admin/registration-mode", json={"mode": "aberto"}).status_code == 422
    r = admin.post(f"{API}/admin/invites", json={"email": "novo@exemplo.com.br"})
    admin.delete(f"{API}/admin/invites/{r.json()['invite']['id']}")
    actions = [log["action"] for log in admin.get(f"{API}/admin/audit-logs").json()]
    for a in ("registration_mode_changed", "invite_created", "invite_revoked"):
        assert a in actions
    # Os registros de auditoria não guardam tokens de convite
    assert r.json()["link"].split("=")[-1] not in admin.get(f"{API}/admin/audit-logs").text


def test_convite_para_email_ja_cadastrado_e_recusado(admin, user_a):
    assert admin.post(f"{API}/admin/invites", json={"email": "ana@exemplo.com.br"}).status_code == 409


def test_promocao_a_admin_somente_pela_cli_do_servidor(mailbox, monkeypatch):
    c = TestClient(app)
    c.post(f"{API}/auth/register", json={"display_name": "Nao Verificado", "email": "nv@exemplo.com.br", "password": PASSWORD})
    monkeypatch.setattr("builtins.input", lambda _: "SIM")
    assert cli.promote_admin("nv@exemplo.com.br") == 1  # e-mail não verificado
    assert cli.promote_admin("inexistente@exemplo.com.br") == 1

    register_and_verify(mailbox, "dono@exemplo.com.br", "Dono")
    assert cli.promote_admin("dono@exemplo.com.br") == 0
    row = owner_exec("SELECT role, status FROM users WHERE email='dono@exemplo.com.br'").one()
    assert tuple(row) == ("ADMIN", "active")
    owner = UserClient()
    assert owner.login("dono@exemplo.com.br").status_code == 200
    # Sem verificação em duas etapas, a administração fica bloqueada
    r = owner.get(f"{API}/admin/stats")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "mfa_setup_required"
    enable_mfa(owner)
    assert owner.get(f"{API}/admin/stats").status_code == 200
