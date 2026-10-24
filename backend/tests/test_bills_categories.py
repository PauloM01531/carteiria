"""Contas recorrentes e categorias personalizadas — regras e isolamento A x B."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.services import bills as bills_svc
from tests.conftest import super_exec

API = "/api/v1"


def cat(client, name, kind=None):
    params = {"include_inactive": "true"}
    if kind:
        params["kind"] = kind
    return next(c["id"] for c in client.get(f"{API}/categories", params=params).json() if c["name"] == name)


def new_bill(client, **over):
    body = {"name": "Aluguel", "amount_type": "fixed", "expected_amount": "1500.00",
            "category_id": cat(client, "Moradia"), "frequency": "monthly", "due_day": 5, "start_date": "2026-09-01"}
    body.update(over)
    r = client.post(f"{API}/bills", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def occ(client, start="2026-09-01", end="2026-12-31"):
    r = client.get(f"{API}/bills/occurrences", params={"start": start, "end": end})
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------ regras de calendário

def _bill(**kw):
    base = dict(frequency="monthly", due_day=5, start_date=date(2026, 1, 1), end_date=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_datas_de_vencimento():
    d = bills_svc.due_dates(_bill(), date(2026, 1, 1), date(2026, 4, 30))
    assert d == [date(2026, 1, 5), date(2026, 2, 5), date(2026, 3, 5), date(2026, 4, 5)]
    # Início no meio do mês pula o vencimento anterior
    assert bills_svc.due_dates(_bill(start_date=date(2026, 1, 10)), date(2026, 1, 1), date(2026, 2, 28)) == [date(2026, 2, 5)]
    # Dia 31 ajustado; trimestral; data final
    assert bills_svc.due_dates(_bill(due_day=31), date(2026, 2, 1), date(2026, 2, 28)) == [date(2026, 2, 28)]
    assert bills_svc.due_dates(_bill(frequency="quarterly"), date(2026, 1, 1), date(2026, 12, 31)) == [
        date(2026, 1, 5), date(2026, 4, 5), date(2026, 7, 5), date(2026, 10, 5)]
    assert bills_svc.due_dates(_bill(end_date=date(2026, 2, 10)), date(2026, 1, 1), date(2026, 12, 31)) == [
        date(2026, 1, 5), date(2026, 2, 5)]
    assert bills_svc.due_dates(_bill(frequency="yearly", start_date=date(2025, 3, 1)), date(2026, 1, 1), date(2026, 12, 31)) == [
        date(2026, 3, 5)]


# ------------------------------------------------------------ contas recorrentes

def test_previsoes_nao_contam_como_despesa_e_nao_duplicam(user_a):
    new_bill(user_a)
    first = occ(user_a)
    assert [o["due_date"] for o in first["items"]] == ["2026-09-05", "2026-10-05", "2026-11-05", "2026-12-05"]
    assert first["summary"]["pending_total"] == "6000.00" and first["summary"]["paid_total"] == "0.00"
    # Consultar de novo não cria ocorrências repetidas
    occ(user_a)
    occ(user_a, "2026-10-01", "2026-10-31")
    assert super_exec("SELECT count(*) FROM bill_occurrences").scalar() == 4
    # Previsão não é despesa
    assert user_a.get(f"{API}/transactions").json()["total"] == 0


def test_pagar_cria_um_lancamento_e_desfazer_remove(user_a):
    new_bill(user_a)
    o = occ(user_a)["items"][1]  # outubro
    r = user_a.post(f"{API}/bills/occurrences/{o['id']}/pay", json={"paid_on": "2026-10-04", "payment_method": "boleto"})
    assert r.status_code == 200 and r.json()["status"] == "paid"
    txs = user_a.get(f"{API}/transactions").json()
    assert txs["total"] == 1 and txs["items"][0]["amount"] == "1500.00" and txs["items"][0]["status"] == "settled"
    assert txs["items"][0]["category_name"] == "Moradia"
    # Pagar de novo é recusado (sem despesa duplicada)
    assert user_a.post(f"{API}/bills/occurrences/{o['id']}/pay", json={"paid_on": "2026-10-04"}).status_code == 409
    assert user_a.get(f"{API}/transactions").json()["total"] == 1

    r = user_a.post(f"{API}/bills/occurrences/{o['id']}/unpay")
    assert r.status_code == 200 and r.json()["status"] != "paid"
    assert user_a.get(f"{API}/transactions").json()["total"] == 0


def test_excluir_o_lancamento_volta_a_conta_para_pendente(user_a):
    new_bill(user_a)
    o = occ(user_a)["items"][0]
    user_a.post(f"{API}/bills/occurrences/{o['id']}/pay", json={"paid_on": "2026-09-05"})
    tx = user_a.get(f"{API}/transactions").json()["items"][0]
    assert user_a.delete(f"{API}/transactions/{tx['id']}").status_code == 200
    assert occ(user_a)["items"][0]["status"] != "paid"


def test_conta_variavel_exige_valor_no_pagamento(user_a):
    new_bill(user_a, name="Energia", amount_type="variable", expected_amount=None, category_id=cat(user_a, "Energia"), due_day=20)
    o = occ(user_a, "2026-10-01", "2026-10-31")["items"][0]
    assert o["amount"] is None
    r = user_a.post(f"{API}/bills/occurrences/{o['id']}/pay", json={"paid_on": "2026-10-19"})
    assert r.status_code == 422
    assert user_a.patch(f"{API}/bills/occurrences/{o['id']}", json={"amount": "187.43"}).json()["amount"] == "187.43"
    r = user_a.post(f"{API}/bills/occurrences/{o['id']}/pay", json={"paid_on": "2026-10-19"})
    assert r.status_code == 200 and r.json()["amount"] == "187.43"


@pytest.mark.parametrize("over", [
    {"amount_type": "fixed", "expected_amount": None},
    {"due_day": 0},
    {"frequency": "daily"},
    {"end_date": "2026-01-01"},
    {"category_id": "SALARIO"},
])
def test_validacao_de_conta(user_a, over):
    if over.get("category_id") == "SALARIO":
        over["category_id"] = cat(user_a, "Salário")
    body = {"name": "X", "amount_type": "fixed", "expected_amount": "10.00", "category_id": cat(user_a, "Moradia"),
            "due_day": 5, "start_date": "2026-09-01", **over}
    assert user_a.post(f"{API}/bills", json=body).status_code == 422


def test_desativar_conta_remove_previsoes_futuras_e_mantem_historico(user_a):
    b = new_bill(user_a, start_date="2026-01-01")
    items = occ(user_a, "2026-01-01", "2026-12-31")["items"]
    user_a.post(f"{API}/bills/occurrences/{items[0]['id']}/pay", json={"paid_on": "2026-01-05"})
    user_a.patch(f"{API}/bills/{b['id']}", json={"active": False})
    after = occ(user_a, "2026-01-01", "2026-12-31")["items"]
    assert any(o["status"] == "paid" for o in after)
    # Ocorrências futuras pendentes foram removidas e não são recriadas
    assert all(o["due_date"] < "2026-10-24" or o["status"] == "paid" for o in after)
    # Excluir a conta mantém o lançamento do pagamento
    assert user_a.delete(f"{API}/bills/{b['id']}").status_code == 200
    assert user_a.get(f"{API}/transactions").json()["total"] == 1


def test_isolamento_contas_recorrentes(user_a, user_b):
    bb = new_bill(user_b, name="Aluguel do Bruno")
    ob = occ(user_b)["items"][0]
    assert user_a.get(f"{API}/bills").json() == []
    assert occ(user_a)["items"] == []
    for method, path, body in [
        ("PATCH", f"/bills/{bb['id']}", {"name": "hack"}),
        ("DELETE", f"/bills/{bb['id']}", None),
        ("POST", f"/bills/occurrences/{ob['id']}/pay", {"paid_on": "2026-09-05"}),
        ("POST", f"/bills/occurrences/{ob['id']}/unpay", None),
        ("PATCH", f"/bills/occurrences/{ob['id']}", {"amount": "1.00"}),
    ]:
        fn = {"PATCH": user_a.patch, "DELETE": user_a.delete, "POST": user_a.post}[method]
        r = fn(API + path, json=body) if body else fn(API + path)
        assert r.status_code == 404, (method, path)
    assert user_b.get(f"{API}/bills").json()[0]["name"] == "Aluguel do Bruno"
    assert occ(user_b)["items"][0]["status"] != "paid"
    assert user_a.get(f"{API}/transactions").json()["total"] == 0


# ------------------------------------------------------------ categorias personalizadas

def test_crud_de_categorias_personalizadas(user_a):
    r = user_a.post(f"{API}/categories", json={"name": "Pet", "kind": "expense"})
    assert r.status_code == 201 and not r.json()["is_system"]
    cid = r.json()["id"]
    # Duplicadas (inclusive com nome de categoria padrão) são recusadas
    assert user_a.post(f"{API}/categories", json={"name": "pet", "kind": "expense"}).status_code == 409
    assert user_a.post(f"{API}/categories", json={"name": "Alimentação", "kind": "expense"}).status_code == 409
    assert user_a.patch(f"{API}/categories/{cid}", json={"name": "Pets"}).json()["name"] == "Pets"

    # Usada em um lançamento, depois desativada: o histórico continua
    tx = user_a.post(f"{API}/transactions", json={"kind": "expense", "description": "Ração", "amount": "80.00",
                                                   "occurred_on": "2026-10-01", "category_id": cid, "payment_method": "pix"}).json()
    assert user_a.patch(f"{API}/categories/{cid}", json={"active": False}).json()["active"] is False
    assert "Pets" not in [c["name"] for c in user_a.get(f"{API}/categories").json()]
    assert user_a.get(f"{API}/transactions/{tx['id']}").json()["category_name"] == "Pets"
    # Não pode ser usada em lançamentos novos, mas o antigo pode ser editado normalmente
    r = user_a.post(f"{API}/transactions", json={"kind": "expense", "description": "Ração", "amount": "80.00",
                                                  "occurred_on": "2026-10-02", "category_id": cid, "payment_method": "pix"})
    assert r.status_code == 422
    assert user_a.patch(f"{API}/transactions/{tx['id']}", json={"amount": "85.00"}).status_code == 200


def test_categorias_padrao_nao_podem_ser_alteradas(user_a):
    alim = cat(user_a, "Alimentação")
    r = user_a.patch(f"{API}/categories/{alim}", json={"active": False})
    assert r.status_code == 403
    assert user_a.post(f"{API}/categories", json={"name": "X", "kind": "expense", "user_id": None}).status_code == 422


def test_isolamento_de_categorias(user_a, user_b):
    cb = user_b.post(f"{API}/categories", json={"name": "Hobby do Bruno", "kind": "expense"}).json()
    assert "Hobby do Bruno" not in [c["name"] for c in user_a.get(f"{API}/categories", params={"include_inactive": "true"}).json()]
    assert user_a.patch(f"{API}/categories/{cb['id']}", json={"name": "hack"}).status_code == 404
    # A pode criar uma categoria com o mesmo nome (são independentes)
    assert user_a.post(f"{API}/categories", json={"name": "Hobby do Bruno", "kind": "expense"}).status_code == 201
    # A não usa a categoria de B em contas recorrentes nem em compras
    body = {"name": "X", "amount_type": "fixed", "expected_amount": "10.00", "category_id": cb["id"], "due_day": 5,
            "start_date": "2026-09-01"}
    assert user_a.post(f"{API}/bills", json=body).status_code == 422
    card = user_a.post(f"{API}/cards", json={"nickname": "C", "closing_day": 1, "due_day": 8}).json()
    r = user_a.post(f"{API}/card-purchases", json={"card_id": card["id"], "description": "x", "total_amount": "10.00",
                                                    "purchase_date": "2026-10-01", "category_id": cb["id"]})
    assert r.status_code == 422
    assert super_exec("SELECT name FROM categories WHERE id=:i", i=cb["id"]).scalar() == "Hobby do Bruno"
