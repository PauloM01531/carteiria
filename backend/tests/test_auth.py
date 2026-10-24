"""Cadastro, verificação de e-mail, login, sessões e recuperação de senha."""
from fastapi.testclient import TestClient

from app.main import app
from app.security.rate_limit import limiter
from tests.conftest import PASSWORD, UserClient, extract_token, make_user, owner_exec, register_and_verify

API = "/api/v1"


def test_fluxo_completo_de_cadastro_com_aprovacao(mailbox):
    c = UserClient()
    r = c.post(f"{API}/auth/register", json={"display_name": "Carla", "email": "Carla@Exemplo.com.br", "password": PASSWORD})
    assert r.status_code == 202
    assert len(mailbox.outbox) == 1 and mailbox.outbox[0].to == "carla@exemplo.com.br"

    # Antes de verificar o e-mail
    r = c.login("carla@exemplo.com.br")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "email_not_verified"

    token = extract_token(mailbox.outbox[0].body, "#token")
    r = c.post(f"{API}/auth/verify-email", json={"token": token})
    assert r.status_code == 200 and "aprovação" in r.json()["message"]

    # Token de verificação é de uso único
    assert c.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 400

    # Verificado, mas aguardando aprovação
    r = c.login("carla@exemplo.com.br")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "pending_approval"

    owner_exec("UPDATE users SET status='active' WHERE email='carla@exemplo.com.br'")
    r = c.login("carla@exemplo.com.br")
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "USER"
    assert c.get(f"{API}/auth/session").status_code == 200


def test_cookie_de_sessao_tem_atributos_de_seguranca(user_a):
    r = UserClient().login("ana@exemplo.com.br")
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    # O token de sessão não aparece no corpo da resposta
    assert r.cookies.get("cw_session") not in r.text


def test_senha_armazenada_com_argon2id(mailbox):
    register_and_verify(mailbox, "dani@exemplo.com.br", "Dani")
    h = owner_exec("SELECT password_hash FROM users WHERE email='dani@exemplo.com.br'").scalar()
    assert h.startswith("$argon2id$") and PASSWORD not in h


def test_senha_fraca_rejeitada(mailbox):
    c = TestClient(app)
    for pwd in ["curta1", "somenteletrasaqui", "1234567890123"]:
        r = c.post(f"{API}/auth/register", json={"display_name": "Eva", "email": "eva@exemplo.com.br", "password": pwd})
        assert r.status_code == 422, pwd
    assert owner_exec("SELECT count(*) FROM users").scalar() == 0


def test_cadastro_duplicado_nao_revela_conta_existente(mailbox, user_a):
    c = TestClient(app)
    r = c.post(f"{API}/auth/register", json={"display_name": "Outra", "email": "ana@exemplo.com.br", "password": PASSWORD})
    assert r.status_code == 202
    assert owner_exec("SELECT count(*) FROM users WHERE email='ana@exemplo.com.br'").scalar() == 1
    assert "Tentativa de cadastro" in mailbox.outbox[-1].subject


def test_campos_extras_como_role_sao_rejeitados(mailbox):
    c = TestClient(app)
    r = c.post(f"{API}/auth/register", json={"display_name": "Fabio", "email": "fabio@exemplo.com.br",
                                             "password": PASSWORD, "role": "ADMIN"})
    assert r.status_code == 422
    assert owner_exec("SELECT count(*) FROM users").scalar() == 0


def test_login_com_erro_tem_mensagem_generica(user_a):
    c = UserClient()
    r1 = c.login("ana@exemplo.com.br", "SenhaErrada999")
    r2 = c.login("ninguem@exemplo.com.br", "SenhaErrada999")
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


def test_limite_de_tentativas_de_login(user_a):
    limiter.reset()
    c = UserClient()
    codes = [c.login("ana@exemplo.com.br", "SenhaErrada999").status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_recuperacao_e_redefinicao_de_senha(mailbox, user_a):
    c = TestClient(app)
    # E-mail inexistente: mesma resposta, nenhum e-mail enviado
    before = len(mailbox.outbox)
    r = c.post(f"{API}/auth/forgot-password", json={"email": "ninguem@exemplo.com.br"})
    assert r.status_code == 202 and len(mailbox.outbox) == before

    r2 = c.post(f"{API}/auth/forgot-password", json={"email": "ana@exemplo.com.br"})
    assert r2.status_code == 202 and r2.json() == r.json()
    token = extract_token(mailbox.outbox[-1].body, "#token")

    new_pwd = "NovaSenha456789"
    # Senha fraca é recusada e o link continua válido
    assert c.post(f"{API}/auth/reset-password", json={"token": token, "password": "fraca"}).status_code == 422
    r = c.post(f"{API}/auth/reset-password", json={"token": token, "password": new_pwd})
    assert r.status_code == 200, r.text
    # Uso único
    assert c.post(f"{API}/auth/reset-password", json={"token": token, "password": new_pwd}).status_code == 400
    # A sessão antiga foi encerrada
    assert user_a.get(f"{API}/auth/session").status_code == 401
    assert UserClient().login("ana@exemplo.com.br").status_code == 401
    assert UserClient().login("ana@exemplo.com.br", new_pwd).status_code == 200


def test_token_de_redefinicao_expirado(mailbox, user_a):
    c = TestClient(app)
    c.post(f"{API}/auth/forgot-password", json={"email": "ana@exemplo.com.br"})
    token = extract_token(mailbox.outbox[-1].body, "#token")
    owner_exec("UPDATE auth_tokens SET expires_at = now() - interval '1 minute'")
    r = c.post(f"{API}/auth/reset-password", json={"token": token, "password": "NovaSenha456789"})
    assert r.status_code == 400


def test_logout_invalida_a_sessao(user_a):
    token = user_a.http.cookies.get("cw_session")
    assert user_a.post(f"{API}/auth/logout").status_code == 200
    thief = TestClient(app)
    thief.cookies.set("cw_session", token)
    assert thief.get(f"{API}/me").status_code == 401


def test_requisicoes_sem_autenticacao_sao_bloqueadas():
    c = TestClient(app)
    for path in ["/me", "/me/preferences", "/me/sessions", "/auth/session", "/admin/users"]:
        assert c.get(API + path).status_code == 401, path


def test_token_invalido_e_sessoes_expiradas(user_a):
    fake = TestClient(app)
    fake.cookies.set("cw_session", "token-inventado-qualquer")
    assert fake.get(f"{API}/me").status_code == 401

    # Expiração absoluta
    owner_exec("UPDATE user_sessions SET expires_at = now() - interval '1 second'")
    assert user_a.get(f"{API}/me").status_code == 401


def test_sessao_expira_por_inatividade(user_a):
    owner_exec("UPDATE user_sessions SET last_seen_at = now() - interval '2 hours'")
    assert user_a.get(f"{API}/me").status_code == 401


def test_csrf_obrigatorio_em_alteracoes(user_a):
    r = user_a.http.patch(f"{API}/me", json={"display_name": "Hacker"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "csrf"
    r = user_a.http.patch(f"{API}/me", json={"display_name": "Hacker"}, headers={"X-CSRF-Token": "x" * 64})
    assert r.status_code == 403
    r = user_a.patch(f"{API}/me", json={"display_name": "Hacker"}, headers={"Origin": "https://site-malicioso.com"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "bad_origin"
    assert user_a.get(f"{API}/me").json()["display_name"] == "Ana Teste"


def test_troca_de_senha_encerra_outras_sessoes(user_a):
    other = UserClient()
    assert other.login("ana@exemplo.com.br").status_code == 200
    r = user_a.post(f"{API}/auth/change-password", json={"current_password": "errada12345", "new_password": "NovaSenha456789"})
    assert r.status_code == 400
    r = user_a.post(f"{API}/auth/change-password", json={"current_password": PASSWORD, "new_password": "NovaSenha456789"})
    assert r.status_code == 200
    assert user_a.get(f"{API}/me").status_code == 200
    assert other.get(f"{API}/me").status_code == 401


def test_usuario_suspenso_perde_acesso_imediatamente(user_a):
    owner_exec("UPDATE users SET status='suspended' WHERE email='ana@exemplo.com.br'")
    assert user_a.get(f"{API}/me").status_code == 401
    r = UserClient().login("ana@exemplo.com.br")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "suspended"


def test_cabecalhos_de_seguranca():
    r = TestClient(app).get(f"{API}/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in r.headers["content-security-policy"]


def test_erro_de_validacao_nao_ecoa_senha():
    r = TestClient(app).post(f"{API}/auth/login", json={"email": "invalido", "password": "MinhaSenhaSecreta1"})
    assert r.status_code == 422 and "MinhaSenhaSecreta1" not in r.text


def test_modo_fechado_bloqueia_cadastro(mailbox):
    owner_exec("""UPDATE app_settings SET value='"closed"' WHERE key='registration_mode'""")
    r = TestClient(app).post(f"{API}/auth/register", json={"display_name": "Gil", "email": "gil@exemplo.com.br", "password": PASSWORD})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "registration_closed"


def test_modo_convite_exige_convite_valido_e_do_mesmo_email(mailbox, admin):
    assert admin.put(f"{API}/admin/registration-mode", json={"mode": "invite"}).status_code == 200
    c = TestClient(app)
    body = {"display_name": "Hugo", "email": "hugo@exemplo.com.br", "password": PASSWORD}
    r = c.post(f"{API}/auth/register", json=body)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "invite_required"

    r = admin.post(f"{API}/admin/invites", json={"email": "hugo@exemplo.com.br"})
    assert r.status_code == 201
    token = extract_token(r.json()["link"], "#convite")
    assert token not in str(owner_exec("SELECT token_hash FROM invites").scalar())

    # Outro e-mail não pode usar o convite do Hugo
    r = c.post(f"{API}/auth/register", json={**body, "email": "intruso@exemplo.com.br", "invite_token": token})
    assert r.status_code == 400

    register_and_verify(mailbox, "hugo@exemplo.com.br", "Hugo", invite_token=token)
    assert UserClient().login("hugo@exemplo.com.br").status_code == 200  # convite = conta já aprovada

    # Convite é de uso único
    r = c.post(f"{API}/auth/register", json={**body, "email": "hugo@exemplo.com.br", "invite_token": token})
    assert r.status_code == 400


def test_convite_revogado_ou_expirado_nao_funciona(mailbox, admin):
    c = TestClient(app)
    r = admin.post(f"{API}/admin/invites", json={"email": "ivo@exemplo.com.br"})
    inv_id, token = r.json()["invite"]["id"], extract_token(r.json()["link"], "#convite")
    assert admin.delete(f"{API}/admin/invites/{inv_id}").status_code == 200
    body = {"display_name": "Ivo", "email": "ivo@exemplo.com.br", "password": PASSWORD, "invite_token": token}
    assert c.post(f"{API}/auth/register", json=body).status_code == 400

    r = admin.post(f"{API}/admin/invites", json={"email": "ivo@exemplo.com.br"})
    token2 = extract_token(r.json()["link"], "#convite")
    owner_exec("UPDATE invites SET expires_at = now() - interval '1 minute' WHERE revoked_at IS NULL")
    assert c.post(f"{API}/auth/register", json={**body, "invite_token": token2}).status_code == 400


def test_reenvio_de_verificacao(mailbox):
    c = TestClient(app)
    c.post(f"{API}/auth/register", json={"display_name": "Jo", "email": "jo@exemplo.com.br", "password": PASSWORD})
    first = extract_token(mailbox.outbox[-1].body, "#token")
    assert c.post(f"{API}/auth/resend-verification", json={"email": "jo@exemplo.com.br"}).status_code == 202
    second = extract_token(mailbox.outbox[-1].body, "#token")
    # Só o link mais recente vale
    assert c.post(f"{API}/auth/verify-email", json={"token": first}).status_code == 400
    assert c.post(f"{API}/auth/verify-email", json={"token": second}).status_code == 200
