"""Receitas e despesas: regras, cálculos, filtros e isolamento entre A e B."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import get_app_engine
from app.main import app
from tests.conftest import PASSWORD, owner_exec, super_exec

API = "/api/v1"


def cat(client, name: str) -> str:
    cats = client.get(f"{API}/categories").json()
    return next(c["id"] for c in cats if c["name"] == name)


def new_tx(client, **over):
    body = {
        "kind": "expense",
        "description": "Mercado",
        "amount": "150.00",
        "occurred_on": "2026-10-05",
        "category_id": cat(client, "Alimentação" if over.get("kind", "expense") == "expense" else "Salário"),
        "payment_method": "pix",
    }
    body.update(over)
    return client.post(f"{API}/transactions", json=body)


def uid(email):
    return owner_exec("SELECT id FROM users WHERE email=:e", e=email).scalar()


def as_app(user_id, sql, **params):
    with get_app_engine().begin() as conn:
        conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user_id) if user_id else ""})
        return conn.execute(text(sql), params)


# ------------------------------------------------------------ Categorias

def test_categorias_padrao_disponiveis(user_a):
    cats = user_a.get(f"{API}/categories").json()
    names = {(c["kind"], c["name"]) for c in cats}
    for n in ["Alimentação", "Moradia", "Energia", "Internet", "Transporte", "Saúde", "Educação",
              "Lazer", "Assinaturas", "Compras", "Outros"]:
        assert ("expense", n) in names
    for n in ["Salário", "Renda extra", "Benefícios", "Reembolsos"]:
        assert ("income", n) in names
    assert all(c["is_system"] for c in cats)
    only_income = user_a.get(f"{API}/categories", params={"kind": "income"}).json()
    assert {c["kind"] for c in only_income} == {"income"}


# ------------------------------------------------------------ CRUD e validação

def test_criar_consultar_editar_excluir(user_a):
    r = new_tx(user_a, notes="  compra   do mês ")
    assert r.status_code == 201, r.text
    tx = r.json()
    assert tx["amount"] == "150.00" and tx["category_name"] == "Alimentação" and tx["status"] == "settled"
    assert tx["notes"] == "compra do mês"

    assert user_a.get(f"{API}/transactions/{tx['id']}").json()["description"] == "Mercado"

    r = user_a.patch(f"{API}/transactions/{tx['id']}", json={"amount": "99.90", "status": "pending"})
    assert r.status_code == 200 and r.json()["amount"] == "99.90" and r.json()["status"] == "pending"

    # Mudar para receita exige categoria de receita
    r = user_a.patch(f"{API}/transactions/{tx['id']}", json={"kind": "income"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "category_kind_mismatch"
    r = user_a.patch(f"{API}/transactions/{tx['id']}", json={"kind": "income", "category_id": cat(user_a, "Reembolsos")})
    assert r.status_code == 200 and r.json()["category_name"] == "Reembolsos"

    assert user_a.delete(f"{API}/transactions/{tx['id']}").status_code == 200
    assert user_a.get(f"{API}/transactions/{tx['id']}").status_code == 404


@pytest.mark.parametrize("over", [
    {"amount": "0"},
    {"amount": "-10.00"},
    {"amount": "10.005"},
    {"amount": "abc"},
    {"amount": "10000000000.00"},
    {"description": "   "},
    {"description": "x" * 201},
    {"kind": "transfer"},
    {"payment_method": "cheque"},
    {"status": "cancelado"},
    {"occurred_on": "1999-12-31"},
    {"occurred_on": "31/10/2026"},
    {"category_id": str(uuid.uuid4())},
])
def test_validacoes_no_backend(user_a, over):
    r = new_tx(user_a, **over)
    assert r.status_code == 422, (over, r.text)
    assert super_exec("SELECT count(*) FROM transactions").scalar() == 0


def test_categoria_de_tipo_errado(user_a):
    r = new_tx(user_a, kind="income", category_id=cat(user_a, "Alimentação"))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "category_kind_mismatch"


def test_campo_obrigatorio_nao_pode_ser_anulado(user_a):
    tx = new_tx(user_a).json()
    assert user_a.patch(f"{API}/transactions/{tx['id']}", json={"amount": None}).status_code == 422


# ------------------------------------------------------------ Cálculos

def test_totais_com_decimais_exatos(user_a):
    # 0,10 + 0,20 deve dar exatamente 0,30 (float daria 0,30000000000000004)
    new_tx(user_a, amount="0.10")
    new_tx(user_a, amount="0.20")
    new_tx(user_a, kind="income", amount="1000.01", description="Salário")
    t = user_a.get(f"{API}/transactions/summary").json()
    assert t == {"income": "1000.01", "expense": "0.30", "balance": "999.71", "count": 3}


def test_saldo_negativo_e_periodo_vazio(user_a):
    new_tx(user_a, amount="500.00")
    new_tx(user_a, kind="income", amount="200.00", description="Freela")
    assert user_a.get(f"{API}/transactions/summary").json()["balance"] == "-300.00"
    empty = user_a.get(f"{API}/transactions/summary", params={"start": "2020-01-01", "end": "2020-01-31"}).json()
    assert empty == {"income": "0.00", "expense": "0.00", "balance": "0.00", "count": 0}


def test_pendentes_entram_somente_quando_filtrados(user_a):
    new_tx(user_a, amount="100.00")
    new_tx(user_a, amount="40.00", status="pending")
    assert user_a.get(f"{API}/transactions/summary", params={"status": "settled"}).json()["expense"] == "100.00"
    assert user_a.get(f"{API}/transactions/summary", params={"status": "pending"}).json()["expense"] == "40.00"


# ------------------------------------------------------------ Filtros

def test_filtros(user_a):
    new_tx(user_a, description="Mercado Bom Preço", occurred_on="2026-09-10", amount="80.00")
    new_tx(user_a, description="Uber", category_id=cat(user_a, "Transporte"), payment_method="credito", occurred_on="2026-10-02", amount="25.50")
    new_tx(user_a, description="Conta de luz", category_id=cat(user_a, "Energia"), payment_method="boleto", status="pending", occurred_on="2026-10-20", amount="180.00")
    new_tx(user_a, kind="income", description="Salário outubro", occurred_on="2026-10-05", amount="3000.00")

    def q(**params):
        return user_a.get(f"{API}/transactions", params=params).json()

    outubro = q(start="2026-10-01", end="2026-10-31")
    assert outubro["total"] == 3
    assert outubro["totals"] == {"income": "3000.00", "expense": "205.50", "balance": "2794.50", "count": 3}
    # Ordenado da data mais recente para a mais antiga
    assert [i["occurred_on"] for i in outubro["items"]] == ["2026-10-20", "2026-10-05", "2026-10-02"]

    assert q(kind="income")["total"] == 1
    assert q(category_id=cat(user_a, "Transporte"))["items"][0]["description"] == "Uber"
    assert q(payment_method="boleto")["items"][0]["description"] == "Conta de luz"
    assert q(status="pending")["total"] == 1
    assert q(q="mercado")["total"] == 1          # sem diferenciar maiúsculas
    assert q(q="%")["total"] == 4               # curingas não têm efeito especial
    assert user_a.get(f"{API}/transactions", params={"start": "2026-10-31", "end": "2026-10-01"}).status_code == 422


def test_paginacao(user_a):
    for i in range(5):
        new_tx(user_a, description=f"Item {i}", occurred_on=f"2026-10-0{i + 1}")
    p1 = user_a.get(f"{API}/transactions", params={"page_size": 2, "page": 1}).json()
    p3 = user_a.get(f"{API}/transactions", params={"page_size": 2, "page": 3}).json()
    assert p1["total"] == 5 and len(p1["items"]) == 2 and len(p3["items"]) == 1
    # Totais consideram todo o filtro, não só a página
    assert p1["totals"]["count"] == 5 and p1["totals"]["expense"] == "750.00"


# ------------------------------------------------------------ Isolamento A x B

def test_a_nao_ve_lancamentos_de_b_e_vice_versa(user_a, user_b):
    new_tx(user_a, description="Despesa da Ana", amount="10.00")
    new_tx(user_b, description="Despesa do Bruno", amount="999.00")
    la = user_a.get(f"{API}/transactions").json()
    lb = user_b.get(f"{API}/transactions").json()
    assert [i["description"] for i in la["items"]] == ["Despesa da Ana"]
    assert [i["description"] for i in lb["items"]] == ["Despesa do Bruno"]
    # Totais e resumo também ficam isolados
    assert la["totals"]["expense"] == "10.00"
    assert user_b.get(f"{API}/transactions/summary").json()["expense"] == "999.00"
    # Busca pelo texto do outro não encontra nada
    assert user_a.get(f"{API}/transactions", params={"q": "Bruno"}).json()["total"] == 0


def test_trocar_id_na_url_nao_da_acesso(user_a, user_b):
    tb = new_tx(user_b, description="Do Bruno").json()
    assert user_a.get(f"{API}/transactions/{tb['id']}").status_code == 404
    assert user_a.patch(f"{API}/transactions/{tb['id']}", json={"amount": "1.00"}).status_code == 404
    assert user_a.delete(f"{API}/transactions/{tb['id']}").status_code == 404
    still = user_b.get(f"{API}/transactions/{tb['id']}").json()
    assert still["amount"] == "150.00" and still["description"] == "Do Bruno"


def test_corpo_nao_falsifica_dono(user_a, user_b):
    b_id = str(uid("bruno@exemplo.com.br"))
    r = new_tx(user_a, user_id=b_id)
    assert r.status_code == 422
    ta = new_tx(user_a).json()
    assert user_a.patch(f"{API}/transactions/{ta['id']}", json={"user_id": b_id}).status_code == 422
    assert user_b.get(f"{API}/transactions").json()["total"] == 0


def test_categoria_privada_de_outro_usuario_nao_pode_ser_usada(user_a, user_b):
    b_id = uid("bruno@exemplo.com.br")
    cat_b = as_app(b_id, "INSERT INTO categories (user_id, name, kind) VALUES (:b, 'Pet do Bruno', 'expense') RETURNING id", b=b_id).scalar()
    # A não vê a categoria de B
    assert "Pet do Bruno" not in [c["name"] for c in user_a.get(f"{API}/categories").json()]
    assert "Pet do Bruno" in [c["name"] for c in user_b.get(f"{API}/categories").json()]
    # Nem consegue usá-la na criação ou na edição
    r = new_tx(user_a, category_id=str(cat_b))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_category"
    ta = new_tx(user_a).json()
    assert user_a.patch(f"{API}/transactions/{ta['id']}", json={"category_id": str(cat_b)}).status_code == 422
    # Filtrar pela categoria de B não revela nada
    assert user_a.get(f"{API}/transactions", params={"category_id": str(cat_b)}).json()["total"] == 0


def test_rls_lancamentos_no_banco(user_a, user_b):
    new_tx(user_a, amount="10.00")
    new_tx(user_b, amount="20.00")
    a, b = uid("ana@exemplo.com.br"), uid("bruno@exemplo.com.br")
    assert as_app(a, "SELECT amount FROM transactions").scalars().all() == [__import__("decimal").Decimal("10.00")]
    assert as_app(None, "SELECT * FROM transactions").all() == []
    assert as_app(a, "UPDATE transactions SET amount = 1 WHERE user_id = :b", b=b).rowcount == 0
    assert as_app(a, "DELETE FROM transactions WHERE user_id = :b", b=b).rowcount == 0
    alim = as_app(a, "SELECT id FROM categories WHERE name='Alimentação'").scalar()
    with pytest.raises(DBAPIError, match="row-level security"):
        as_app(a, """INSERT INTO transactions (user_id, kind, description, amount, occurred_on, category_id, payment_method)
                     VALUES (:b, 'expense', 'x', 1, '2026-10-01', :c, 'pix')""", b=b, c=alim)


def test_trigger_impede_categoria_alheia_mesmo_sem_a_api(user_a, user_b):
    a, b = uid("ana@exemplo.com.br"), uid("bruno@exemplo.com.br")
    cat_b = as_app(b, "INSERT INTO categories (user_id, name, kind) VALUES (:b, 'Privada B', 'expense') RETURNING id", b=b).scalar()
    with pytest.raises(DBAPIError, match="categoria nao pertence"):
        as_app(a, """INSERT INTO transactions (user_id, kind, description, amount, occurred_on, category_id, payment_method)
                     VALUES (:a, 'expense', 'x', 1, '2026-10-01', :c, 'pix')""", a=a, c=cat_b)


def test_categorias_do_sistema_sao_somente_leitura(user_a):
    a = uid("ana@exemplo.com.br")
    assert as_app(a, "UPDATE categories SET name='Hackeada' WHERE user_id IS NULL").rowcount == 0
    with pytest.raises(DBAPIError, match="row-level security"):
        as_app(a, "INSERT INTO categories (user_id, name, kind) VALUES (NULL, 'Global falsa', 'expense')")
    with pytest.raises(DBAPIError, match="permission denied"):
        as_app(a, "DELETE FROM categories")


def test_sem_autenticacao_e_sem_csrf(user_a):
    c = TestClient(app)
    assert c.get(f"{API}/transactions").status_code == 401
    assert c.get(f"{API}/categories").status_code == 401
    assert c.post(f"{API}/transactions", json={}).status_code in (401, 422)
    r = user_a.http.post(f"{API}/transactions", json={
        "kind": "expense", "description": "x", "amount": "1.00", "occurred_on": "2026-10-01",
        "category_id": cat(user_a, "Outros"), "payment_method": "pix"})
    assert r.status_code == 403


def test_exclusao_da_conta_remove_lancamentos(user_a, user_b):
    new_tx(user_a)
    new_tx(user_b)
    assert user_a.delete(f"{API}/me", json={"password": PASSWORD, "confirmation": "EXCLUIR"}).status_code == 200
    assert super_exec("SELECT count(*) FROM transactions").scalar() == 1
    assert user_b.get(f"{API}/transactions").json()["total"] == 1
