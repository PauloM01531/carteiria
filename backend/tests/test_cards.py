"""Cartões, compras parceladas, faturas e pagamentos pela API — incluindo isolamento A x B."""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import get_app_engine
from tests.conftest import PASSWORD, owner_exec, super_exec

API = "/api/v1"


def cat(client, name):
    return next(c["id"] for c in client.get(f"{API}/categories").json() if c["name"] == name)


def new_card(client, **over):
    body = {"nickname": "Nubank", "institution": "Nu", "closing_day": 10, "due_day": 17, "credit_limit": "5000.00"}
    body.update(over)
    r = client.post(f"{API}/cards", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def new_purchase(client, card_ref, **over):
    body = {"card_id": card_ref, "description": "Notebook", "total_amount": "1200.00", "purchase_date": "2026-10-05",
            "category_id": cat(client, "Compras"), "installments_count": 12}
    body.update(over)
    return client.post(f"{API}/card-purchases", json=body)


def uid(email):
    return owner_exec("SELECT id FROM users WHERE email=:e", e=email).scalar()


def as_app(user_id, sql, **params):
    with get_app_engine().begin() as conn:
        conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user_id) if user_id else ""})
        return conn.execute(text(sql), params)


# ------------------------------------------------------------ cartões

def test_crud_de_cartao(user_a):
    card = new_card(user_a)
    assert card["used_amount"] == "0.00" and card["available_limit"] == "5000.00"
    r = user_a.patch(f"{API}/cards/{card['id']}", json={"nickname": "Roxinho", "active": False})
    assert r.status_code == 200 and r.json()["nickname"] == "Roxinho" and not r.json()["active"]
    assert user_a.delete(f"{API}/cards/{card['id']}").status_code == 200


@pytest.mark.parametrize("over", [{"closing_day": 0}, {"closing_day": 32}, {"due_day": -1},
                                  {"credit_limit": "-1"}, {"nickname": " "}, {"user_id": str(uuid.uuid4())}])
def test_validacao_de_cartao(user_a, over):
    body = {"nickname": "X", "closing_day": 10, "due_day": 17, **over}
    assert user_a.post(f"{API}/cards", json=body).status_code == 422


def test_cartao_com_compras_nao_pode_ser_excluido(user_a):
    card = new_card(user_a)
    new_purchase(user_a, card["id"])
    r = user_a.delete(f"{API}/cards/{card['id']}")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "card_in_use"


def test_cartao_inativo_nao_aceita_compras(user_a):
    card = new_card(user_a)
    user_a.patch(f"{API}/cards/{card['id']}", json={"active": False})
    assert new_purchase(user_a, card["id"]).status_code == 422


# ------------------------------------------------------------ compras e faturas

def test_compra_1200_em_12x_gera_100_por_fatura(user_a):
    card = new_card(user_a)
    r = new_purchase(user_a, card["id"])  # 05/10, fechamento dia 10 -> 1ª fatura em outubro
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["first_statement_month"] == "2026-10-01"
    assert [i["amount"] for i in p["installments"]] == ["100.00"] * 12
    assert [i["reference_month"] for i in p["installments"]][:3] == ["2026-10-01", "2026-11-01", "2026-12-01"]
    assert p["installments"][-1]["reference_month"] == "2027-09-01"

    sts = user_a.get(f"{API}/statements", params={"card_id": card["id"]}).json()
    assert len(sts) == 12
    assert all(s["total"] == "100.00" for s in sts)  # R$ 100 em cada fatura, nunca R$ 1.200
    # Limite comprometido = total ainda não pago
    assert user_a.get(f"{API}/cards/{card['id']}").json()["used_amount"] == "1200.00"
    assert user_a.get(f"{API}/cards/{card['id']}").json()["available_limit"] == "3800.00"
    # Compras de cartão NÃO viram lançamentos (evita contar duas vezes)
    assert user_a.get(f"{API}/transactions").json()["total"] == 0


def test_varias_compras_somam_na_mesma_fatura_sem_duplicar(user_a):
    card = new_card(user_a)
    new_purchase(user_a, card["id"], total_amount="100.00", installments_count=3)   # 33,33/33,33/33,34
    new_purchase(user_a, card["id"], total_amount="50.00", installments_count=1, description="Farmácia",
                 category_id=cat(user_a, "Saúde"))
    sts = user_a.get(f"{API}/statements", params={"card_id": card["id"]}).json()
    assert [s["total"] for s in sts] == ["83.33", "33.33", "33.34"]
    assert super_exec("SELECT count(*) FROM card_statements").scalar() == 3  # uma fatura por competência
    detail = user_a.get(f"{API}/statements/{sts[0]['id']}").json()
    assert {(i["description"], i["number"], i["installments_count"]) for i in detail["items"]} == {
        ("Notebook", 1, 3), ("Farmácia", 1, 1)}


def test_competencia_editavel(user_a):
    card = new_card(user_a)
    p = new_purchase(user_a, card["id"], installments_count=2, first_statement_month="2026-12-15").json()
    assert p["first_statement_month"] == "2026-12-01"
    assert [i["reference_month"] for i in p["installments"]] == ["2026-12-01", "2027-01-01"]


def test_sugestao_de_fatura(user_a):
    card = new_card(user_a, closing_day=10, due_day=17)
    s = user_a.get(f"{API}/cards/{card['id']}/suggest-statement", params={"purchase_date": "2026-10-10"}).json()
    assert s == {"reference_month": "2026-11-01", "closing_date": "2026-11-10", "due_date": "2026-11-17"}


def test_editar_compra_refaz_parcelas_e_limpa_faturas_vazias(user_a):
    card = new_card(user_a)
    p = new_purchase(user_a, card["id"]).json()
    r = user_a.patch(f"{API}/card-purchases/{p['id']}", json={"installments_count": 3, "total_amount": "300.00"})
    assert r.status_code == 200
    assert [i["amount"] for i in r.json()["installments"]] == ["100.00"] * 3
    assert len(user_a.get(f"{API}/statements").json()) == 3  # as 9 faturas vazias foram removidas
    # Editar só a descrição não mexe nas parcelas
    ids_before = [i["id"] for i in r.json()["installments"]]
    r2 = user_a.patch(f"{API}/card-purchases/{p['id']}", json={"description": "Notebook novo"})
    assert [i["id"] for i in r2.json()["installments"]] == ids_before


def test_excluir_compra_remove_parcelas(user_a):
    card = new_card(user_a)
    p = new_purchase(user_a, card["id"]).json()
    assert user_a.delete(f"{API}/card-purchases/{p['id']}").status_code == 200
    assert super_exec("SELECT count(*) FROM installments").scalar() == 0
    assert user_a.get(f"{API}/statements").json() == []


def test_pagamento_de_fatura(user_a):
    card = new_card(user_a)
    new_purchase(user_a, card["id"], installments_count=12)
    st = user_a.get(f"{API}/statements", params={"card_id": card["id"]}).json()[0]

    r = user_a.post(f"{API}/statements/{st['id']}/payments", json={"amount": "150.00", "paid_on": "2026-10-17"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "overpayment"
    r = user_a.post(f"{API}/statements/{st['id']}/payments", json={"amount": "40.00", "paid_on": "2026-10-15"})
    assert r.status_code == 201
    d = user_a.get(f"{API}/statements/{st['id']}").json()
    assert (d["paid"], d["remaining"]) == ("40.00", "60.00") and d["status"] in ("partial", "overdue")
    pay2 = user_a.post(f"{API}/statements/{st['id']}/payments", json={"amount": "60.00", "paid_on": "2026-10-17"}).json()
    d = user_a.get(f"{API}/statements/{st['id']}").json()
    assert d["status"] == "paid" and d["remaining"] == "0.00" and len(d["payments"]) == 2
    # Fatura paga libera o limite
    assert user_a.get(f"{API}/cards/{card['id']}").json()["used_amount"] == "1100.00"
    # Pagamento de fatura NÃO cria despesa nova (a despesa é a compra)
    assert user_a.get(f"{API}/transactions").json()["total"] == 0

    # Compra em fatura com pagamento fica travada para alteração de valores
    pid = user_a.get(f"{API}/card-purchases").json()[0]["id"]
    r = user_a.patch(f"{API}/card-purchases/{pid}", json={"total_amount": "999.00"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "statement_has_payment"
    assert user_a.delete(f"{API}/card-purchases/{pid}").status_code == 409

    assert user_a.delete(f"{API}/statements/{st['id']}/payments/{pay2['id']}").status_code == 200
    assert user_a.get(f"{API}/statements/{st['id']}").json()["paid"] == "40.00"


def test_validacoes_de_compra(user_a):
    card = new_card(user_a)
    for over in [{"installments_count": 0}, {"installments_count": 73}, {"total_amount": "0"},
                 {"category_id": cat(user_a, "Salário")}, {"category_id": str(uuid.uuid4())},
                 {"card_id": str(uuid.uuid4())}]:
        r = new_purchase(user_a, card["id"], **over)
        assert r.status_code in (404, 422), (over, r.text)
    assert super_exec("SELECT count(*) FROM card_purchases").scalar() == 0


# ------------------------------------------------------------ isolamento A x B

def test_a_nao_acessa_cartoes_compras_parcelas_e_faturas_de_b(user_a, user_b):
    card_b = new_card(user_b, nickname="Cartão do Bruno")
    pb = new_purchase(user_b, card_b["id"]).json()
    st_b = user_b.get(f"{API}/statements").json()[0]

    # Listagens de A não mostram nada de B
    assert user_a.get(f"{API}/cards").json() == []
    assert user_a.get(f"{API}/card-purchases").json() == []
    assert user_a.get(f"{API}/statements").json() == []
    assert user_a.get(f"{API}/statements", params={"card_id": card_b["id"]}).json() == []
    assert user_a.get(f"{API}/card-purchases", params={"card_id": card_b["id"]}).json() == []

    # Trocar o ID na URL não dá acesso
    for method, path, body in [
        ("GET", f"/cards/{card_b['id']}", None),
        ("PATCH", f"/cards/{card_b['id']}", {"nickname": "hack"}),
        ("DELETE", f"/cards/{card_b['id']}", None),
        ("GET", f"/cards/{card_b['id']}/suggest-statement?purchase_date=2026-10-01", None),
        ("GET", f"/card-purchases/{pb['id']}", None),
        ("PATCH", f"/card-purchases/{pb['id']}", {"description": "hack"}),
        ("DELETE", f"/card-purchases/{pb['id']}", None),
        ("GET", f"/statements/{st_b['id']}", None),
        ("POST", f"/statements/{st_b['id']}/payments", {"amount": "1.00", "paid_on": "2026-10-10"}),
    ]:
        fn = {"GET": user_a.get, "PATCH": user_a.patch, "DELETE": user_a.delete, "POST": user_a.post}[method]
        r = fn(API + path, json=body) if body else fn(API + path)
        assert r.status_code == 404, (method, path, r.status_code)

    # Operações relacionadas: A não registra compra no cartão de B nem move sua compra para lá
    card_a = new_card(user_a)
    assert new_purchase(user_a, card_b["id"]).status_code == 404
    pa = new_purchase(user_a, card_a["id"]).json()
    assert user_a.patch(f"{API}/card-purchases/{pa['id']}", json={"card_id": card_b["id"]}).status_code == 404

    # Nada de B mudou
    assert user_b.get(f"{API}/card-purchases/{pb['id']}").json()["description"] == "Notebook"
    assert user_b.get(f"{API}/statements/{st_b['id']}").json()["paid"] == "0.00"
    assert user_b.get(f"{API}/cards/{card_b['id']}").json()["used_amount"] == "1200.00"


def test_a_nao_apaga_pagamento_de_b_mesmo_combinando_ids(user_a, user_b):
    card_b = new_card(user_b)
    new_purchase(user_b, card_b["id"])
    st_b = user_b.get(f"{API}/statements").json()[0]
    pay_b = user_b.post(f"{API}/statements/{st_b['id']}/payments", json={"amount": "10.00", "paid_on": "2026-10-10"}).json()
    card_a = new_card(user_a)
    new_purchase(user_a, card_a["id"])
    st_a = user_a.get(f"{API}/statements").json()[0]
    assert user_a.delete(f"{API}/statements/{st_a['id']}/payments/{pay_b['id']}").status_code == 404
    assert user_a.delete(f"{API}/statements/{st_b['id']}/payments/{pay_b['id']}").status_code == 404
    assert user_b.get(f"{API}/statements/{st_b['id']}").json()["paid"] == "10.00"


def test_rls_e_gatilhos_no_banco(user_a, user_b):
    card_b = new_card(user_b)
    new_purchase(user_b, card_b["id"])
    a, b = uid("ana@exemplo.com.br"), uid("bruno@exemplo.com.br")
    for table in ["cards", "card_statements", "card_purchases", "installments"]:
        assert as_app(a, f"SELECT count(*) FROM {table}").scalar() == 0, table
        assert as_app(b, f"SELECT count(*) FROM {table}").scalar() > 0, table
        assert as_app(a, f"DELETE FROM {table}").rowcount == 0, table
    # A tenta criar fatura (com seu próprio user_id) apontando para o cartão de B: o gatilho recusa
    with pytest.raises(DBAPIError, match="outro usuario"):
        as_app(a, """INSERT INTO card_statements (user_id, card_id, reference_month, closing_date, due_date)
                     VALUES (:a, :c, '2030-01-01', '2030-01-10', '2030-01-17')""", a=a, c=card_b["id"])
    # E não consegue inserir em nome de B
    with pytest.raises(DBAPIError, match="row-level security"):
        as_app(a, """INSERT INTO cards (user_id, nickname, closing_day, due_day) VALUES (:b, 'x', 1, 2)""", b=b)


def test_exclusao_da_conta_remove_cartoes_e_faturas(user_a, user_b):
    card_a = new_card(user_a)
    new_purchase(user_a, card_a["id"])
    card_b = new_card(user_b)
    new_purchase(user_b, card_b["id"], installments_count=2)
    assert user_a.delete(f"{API}/me", json={"password": PASSWORD, "confirmation": "EXCLUIR"}).status_code == 200
    assert super_exec("SELECT count(*) FROM cards").scalar() == 1
    assert super_exec("SELECT count(*) FROM installments").scalar() == 2
    assert len(user_b.get(f"{API}/statements").json()) == 2
