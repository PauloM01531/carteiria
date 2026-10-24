"""Etapa 6: MFA, reautenticação, cobertura de autenticação em TODAS as rotas e proteções contra abuso."""
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import PASSWORD, UserClient, enable_mfa, owner_exec, super_exec, totp_code

API = "/api/v1"

# Rotas que podem ser usadas sem sessão (todas as demais exigem login).
PUBLIC = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/verify-email"),
    ("POST", "/api/v1/auth/resend-verification"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/login/mfa"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/forgot-password"),
    ("POST", "/api/v1/auth/reset-password"),
}


def all_routes():
    spec = app.openapi()
    for path, ops in spec["paths"].items():
        for method in ops:
            yield method.upper(), path


def concrete(path: str) -> str:
    path = path.replace("{dataset}", "lancamentos")
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


def test_existem_rotas_suficientes_para_o_teste_ser_significativo():
    assert len(list(all_routes())) > 60


@pytest.mark.parametrize("method,path", sorted(set(all_routes()) - PUBLIC))
def test_toda_rota_privada_exige_autenticacao(method, path):
    r = TestClient(app).request(method, concrete(path), json={} if method in ("POST", "PUT", "PATCH", "DELETE") else None)
    assert r.status_code == 401, (method, path, r.status_code, r.text[:200])


def test_toda_rota_admin_bloqueia_usuario_comum(user_a):
    admin_routes = [(m, p) for m, p in all_routes() if p.startswith("/api/v1/admin")]
    assert len(admin_routes) >= 10
    for method, path in admin_routes:
        r = user_a.http.request(method, concrete(path), json={} if method != "GET" else None,
                                headers={"X-CSRF-Token": user_a.csrf})
        assert r.status_code == 403, (method, path, r.status_code)


# ------------------------------------------------------------ MFA

def test_fluxo_de_mfa_no_login(user_a):
    r = user_a.post(f"{API}/me/mfa/setup", json={"password": "errada12345"})
    assert r.status_code == 400
    secret = user_a.post(f"{API}/me/mfa/setup", json={"password": PASSWORD}).json()["secret"]
    assert user_a.post(f"{API}/me/mfa/enable", json={"code": "000000"}).status_code == 400
    assert user_a.post(f"{API}/me/mfa/enable", json={"code": totp_code(secret)}).status_code == 200
    assert user_a.get(f"{API}/me").json()["mfa_enabled"] is True

    # O segredo fica cifrado no banco
    stored = owner_exec("SELECT mfa_secret_enc FROM users WHERE email='ana@exemplo.com.br'").scalar()
    assert stored and secret not in stored

    c = UserClient()
    r = c.login("ana@exemplo.com.br")
    assert r.status_code == 200 and r.json()["mfa_required"] is True and "csrf_token" not in r.json()
    assert c.http.cookies.get("cw_session") is None  # nenhuma sessão antes do 2º fator
    challenge = r.json()["challenge"]
    bad = c.http.post(f"{API}/auth/login/mfa", json={"challenge": challenge, "code": "123456"})
    assert bad.status_code == 401
    # Código do passo já usado na ativação é recusado (sem reutilização)
    assert c.http.post(f"{API}/auth/login/mfa", json={"challenge": challenge, "code": totp_code(secret)}).status_code == 401
    ok = c.http.post(f"{API}/auth/login/mfa", json={"challenge": challenge, "code": totp_code(secret, 1)})
    assert ok.status_code == 200, ok.text
    assert c.http.get(f"{API}/me").status_code == 200
    # O desafio é de uso único
    assert UserClient().http.post(f"{API}/auth/login/mfa", json={"challenge": challenge, "code": totp_code(secret, 1)}).status_code == 401


def test_desafio_de_mfa_expira(user_a):
    secret = enable_mfa(user_a)
    r = UserClient().login("ana@exemplo.com.br")
    owner_exec("UPDATE auth_tokens SET expires_at = now() - interval '1 second' WHERE purpose='mfa_challenge'")
    r2 = TestClient(app).post(f"{API}/auth/login/mfa", json={"challenge": r.json()["challenge"], "code": totp_code(secret, 1)})
    assert r2.status_code == 401


def test_admin_nao_pode_desativar_mfa_e_usuario_pode(admin, user_a):
    r = admin.post(f"{API}/me/mfa/disable", json={"password": PASSWORD, "code": totp_code(admin.mfa_secret, 1)})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "admin_requires_mfa"
    secret = enable_mfa(user_a)
    r = user_a.post(f"{API}/me/mfa/disable", json={"password": PASSWORD, "code": totp_code(secret, 1)})
    assert r.status_code == 200
    assert UserClient().login("ana@exemplo.com.br").json().get("csrf_token")


def test_sessao_admin_sem_segundo_fator_e_bloqueada(admin):
    # Simula uma sessão aberta antes da confirmação do 2º fator
    super_exec("UPDATE user_sessions SET mfa_verified = false")
    r = admin.get(f"{API}/admin/users")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "mfa_required"


def test_operacoes_criticas_exigem_reautenticacao(admin, user_b):
    b_id = owner_exec("SELECT id FROM users WHERE email='bruno@exemplo.com.br'").scalar()
    super_exec("UPDATE user_sessions SET reauth_at = now() - interval '11 minutes'")
    # Leitura continua liberada
    assert admin.get(f"{API}/admin/users").status_code == 200
    # Ações críticas pedem confirmação de identidade
    for method, path, body in [
        ("POST", f"/admin/users/{b_id}/suspend", None),
        ("PUT", "/admin/registration-mode", {"mode": "closed"}),
        ("POST", "/admin/invites", {"email": "x@exemplo.com.br"}),
    ]:
        fn = {"POST": admin.post, "PUT": admin.put}[method]
        r = fn(API + path, json=body) if body else fn(API + path)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "reauth_required", path
    assert admin.post(f"{API}/auth/reauth", json={"password": PASSWORD, "code": "000000"}).status_code == 400
    assert admin.post(f"{API}/auth/reauth", json={"password": PASSWORD, "code": totp_code(admin.mfa_secret, 1)}).status_code == 200
    assert admin.post(f"{API}/admin/users/{b_id}/suspend").status_code == 200


def test_cli_remove_mfa_e_encerra_sessoes(admin, monkeypatch):
    from app import cli

    monkeypatch.setattr("builtins.input", lambda _: "SIM")
    assert cli.reset_mfa("admin@exemplo.com.br") == 0
    assert admin.get(f"{API}/me").status_code == 401
    assert owner_exec("SELECT mfa_enabled_at FROM users WHERE email='admin@exemplo.com.br'").scalar() is None


# ------------------------------------------------------------ abuso e entradas maliciosas

def test_corpo_grande_demais_e_recusado(user_a):
    r = user_a.post(f"{API}/transactions", content=b"x" * (300 * 1024), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_tentativas_de_sql_injection_nao_vazam_dados(user_a, user_b):
    cat = next(c["id"] for c in user_b.get(f"{API}/categories").json() if c["name"] == "Lazer")
    user_b.post(f"{API}/transactions", json={"kind": "expense", "description": "Segredo do Bruno", "amount": "10.00",
                                             "occurred_on": "2026-10-01", "category_id": cat, "payment_method": "pix"})
    for q in ["' OR '1'='1", "%' OR 1=1 --", "'; DROP TABLE transactions; --", "\\x00", "Bruno' UNION SELECT * FROM users --"]:
        r = user_a.get(f"{API}/transactions", params={"q": q})
        assert r.status_code == 200 and r.json()["total"] == 0, q
    assert user_b.get(f"{API}/transactions").json()["total"] == 1


def test_xss_e_armazenado_como_texto_e_nunca_executado_pela_api(user_a):
    cat = next(c["id"] for c in user_a.get(f"{API}/categories").json() if c["name"] == "Lazer")
    payload = "<img src=x onerror=alert(1)>"
    r = user_a.post(f"{API}/transactions", json={"kind": "expense", "description": payload, "amount": "1.00",
                                                  "occurred_on": "2026-10-01", "category_id": cat, "payment_method": "pix"})
    assert r.status_code == 201
    # A API responde JSON (nunca HTML) e com CSP que proíbe tudo; o React exibe como texto.
    g = user_a.get(f"{API}/transactions")
    assert g.headers["content-type"].startswith("application/json")
    assert "default-src 'none'" in g.headers["content-security-policy"]
    # Nomes de exibição com tags são recusados
    assert user_a.patch(f"{API}/me", json={"display_name": "<script>x</script>"}).status_code == 422


def test_limite_global_de_requisicoes(monkeypatch):
    import app.main as main
    from app.security.rate_limit import limiter

    limiter.reset()

    monkeypatch.setattr(main, "GLOBAL_LIMIT", 5)
    # O limite é lido na criação do app; recriamos para o teste
    test_app = main.create_app()
    c = TestClient(test_app)
    codes = [c.get(f"{API}/health").status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[-1] == 429
