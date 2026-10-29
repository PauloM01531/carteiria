"""Compras planejadas: cronograma, análise mês a mês, falta de dados, ausência de dupla contagem e isolamento A x B."""
from decimal import Decimal

import pytest

from app.services.calendar import add_months, first_of_month, today
from app.services.planned import schedule
from tests.conftest import PASSWORD, super_exec

API = "/api/v1"
D = Decimal

CUR = first_of_month(today())
M1 = add_months(CUR, 2)          # mês futuro sem lançamentos
HIST = [add_months(CUR, -i) for i in (1, 2, 3)]


def iso(d):
    return d.isoformat()


def cat(client, name):
    return next(c["id"] for c in client.get(f"{API}/categories", params={"include_inactive": "true"}).json() if c["name"] == name)


def tx(client, kind, amount, day, category, desc="x", status="settled"):
    r = client.post(f"{API}/transactions", json={"kind": kind, "description": desc, "amount": amount, "occurred_on": iso(day),
                                                  "category_id": cat(client, category), "payment_method": "pix", "status": status})
    assert r.status_code == 201, r.text
    return r.json()


def with_history(client, income="5000.00", variable="1500.00"):
    """3 meses completos de histórico real: receita e gastos do dia a dia."""
    for m in HIST:
        tx(client, "income", income, m.replace(day=5), "Salário")
        tx(client, "expense", variable, m.replace(day=10), "Alimentação")


def plan(client, **over):
    body = {"name": "Tablet", "total_amount": "2600.00", "installments_count": 12, "first_installment_date": iso(M1.replace(day=10)),
            "category_id": cat(client, "Compras")}
    body.update(over)
    return client.post(f"{API}/planned-purchases", json=body)


def analysis(client, pid):
    r = client.get(f"{API}/planned-purchases/{pid}/analysis")
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------ cronograma

def test_cronograma_tablet_2600_em_12x():
    s = schedule(D("2600.00"), 12, M1)
    assert [v for _, v in s][:11] == [D("216.66")] * 11 and s[-1][1] == D("216.74")
    assert sum(v for _, v in s) == D("2600.00")
    assert s[0][0] == M1 and s[-1][0] == add_months(M1, 11)


# ------------------------------------------------------------ análise

def test_analise_com_todos_os_compromissos(user_a):
    with_history(user_a)
    # Conta fixa de R$ 1.000 (vence dia 15), compra no cartão 1.200 em 12x a partir de M1, outra compra planejada 600 em 3x
    user_a.post(f"{API}/bills", json={"name": "Aluguel", "amount_type": "fixed", "expected_amount": "1000.00",
                                      "category_id": cat(user_a, "Moradia"), "due_day": 15, "start_date": iso(CUR)})
    card = user_a.post(f"{API}/cards", json={"nickname": "Cartão", "closing_day": 10, "due_day": 17, "credit_limit": "50000.00"}).json()
    user_a.post(f"{API}/card-purchases", json={"card_id": card["id"], "description": "Geladeira", "total_amount": "1200.00",
                                               "purchase_date": iso(CUR.replace(day=2)), "category_id": cat(user_a, "Compras"),
                                               "installments_count": 12, "first_statement_month": iso(M1)})
    assert plan(user_a, name="Fone", total_amount="600.00", installments_count=3).status_code == 201
    p = plan(user_a).json()
    assert p["installment_amount"] == "216.66" and p["last_installment_amount"] == "216.74"
    assert p["first_month"] == iso(M1) and p["last_month"] == iso(add_months(M1, 11))

    a = analysis(user_a, p["id"])
    m = a["months"][0]
    assert m["month"] == iso(M1) and m["number"] == 1
    assert (m["income"], m["income_source"]) == ("5000.00", "media")
    assert m["variable_estimate"] == "1500.00"
    assert m["bills_pending"] == "1000.00"
    assert m["card_installments"] == "100.00"      # parcela de cartão já cadastrada, contada uma vez
    assert m["other_planned"] == "200.00"          # a outra compra planejada
    assert m["committed"] == "2800.00"
    assert (m["balance_before"], m["balance_after"]) == ("2200.00", "1983.34")
    assert m["status"] == "fits"
    # O limite do cartão (R$ 50.000) não aparece como dinheiro em lugar nenhum
    assert "50.000" not in str(a)
    # A própria compra planejada não vira parcela de cartão nem lançamento (não altera relatórios)
    assert user_a.get(f"{API}/reports/summary", params={"month": iso(M1)}).json()["expense"] == "100.00"
    # Depois das 3 parcelas da outra compra, ela deixa de pesar
    assert a["months"][3]["other_planned"] == "0.00"


def test_classificacao_atencao_e_acima(user_a):
    with_history(user_a)  # sobra antes = 5.000 − 1.500 = 3.500
    over = plan(user_a, name="Carro", total_amount="4000.00", installments_count=1).json()
    a = analysis(user_a, over["id"])
    assert a["months"][0]["status"] == "over" and a["months"][0]["balance_after"] == "-500.00"
    assert any("faltariam" in f for f in a["months"][0]["factors"])
    assert a["overall_status"] == "over" and "Acima do orçamento" in a["headline"]
    user_a.delete(f"{API}/planned-purchases/{over['id']}")

    tight = plan(user_a, name="Notebook", total_amount="3200.00", installments_count=1).json()  # sobra 300 < 10% de 5.000
    m = analysis(user_a, tight["id"])["months"][0]
    assert m["status"] == "attention" and m["balance_after"] == "300.00"
    assert any("menos de 10%" in f for f in m["factors"])
    user_a.delete(f"{API}/planned-purchases/{tight['id']}")

    share = plan(user_a, name="TV", total_amount="2000.00", installments_count=1).json()  # 57% da sobra
    m = analysis(user_a, share["id"])["months"][0]
    assert m["status"] == "attention" and any("consome" in f for f in m["factors"])


def test_sem_dados_suficientes(user_a):
    card = user_a.post(f"{API}/cards", json={"nickname": "C", "closing_day": 10, "due_day": 17, "credit_limit": "99999.00"}).json()
    assert card["available_limit"] == "99999.00"
    p = plan(user_a).json()
    assert p["overall_status"] == "insufficient"
    a = analysis(user_a, p["id"])
    m = a["months"][0]
    assert m["status"] == "insufficient" and m["income"] is None and m["balance_after"] is None
    assert any("histórico suficiente" in n for n in m["notes"])
    assert a["confidence_notes"]  # explica a limitação
    # Só um mês com receita ainda não é suficiente para estimar
    tx(user_a, "income", "4000.00", HIST[0].replace(day=5), "Salário")
    assert analysis(user_a, p["id"])["months"][0]["status"] == "insufficient"


def test_receita_lancada_no_mes_tem_prioridade_e_analise_atualiza(user_a):
    with_history(user_a)
    p = plan(user_a, total_amount="1000.00", installments_count=1).json()
    assert analysis(user_a, p["id"])["months"][0]["balance_after"] == "2500.00"
    # Receita do mês lançada (pendente) substitui a média
    tx(user_a, "income", "7000.00", M1.replace(day=5), "Salário", status="pending")
    m = analysis(user_a, p["id"])["months"][0]
    assert (m["income"], m["income_source"]) == ("7000.00", "registrada")
    # Despesa grande lançada no mês: entra uma vez e a estimativa do dia a dia é descontada
    tx(user_a, "expense", "2000.00", M1.replace(day=8), "Lazer", status="pending")
    m = analysis(user_a, p["id"])["months"][0]
    assert (m["registered_expenses"], m["variable_estimate"], m["committed"]) == ("2000.00", "0.00", "2000.00")
    assert m["balance_after"] == "4000.00"


def test_conta_fixa_paga_nao_conta_duas_vezes(user_a):
    with_history(user_a)
    user_a.post(f"{API}/bills", json={"name": "Internet", "amount_type": "fixed", "expected_amount": "100.00",
                                      "category_id": cat(user_a, "Internet"), "due_day": 1, "start_date": iso(CUR)})
    occ = user_a.get(f"{API}/bills/occurrences", params={"start": iso(CUR), "end": iso(add_months(CUR, 1).replace(day=1))}).json()
    first = next(o for o in occ["items"] if o["due_date"] == iso(CUR))
    user_a.post(f"{API}/bills/occurrences/{first['id']}/pay", json={"paid_on": iso(CUR), "payment_method": "pix"})
    p = plan(user_a, total_amount="100.00", installments_count=1, first_installment_date=iso(CUR)).json()
    m = analysis(user_a, p["id"])["months"][0]
    assert m["bills_pending"] == "0.00"           # já paga: virou lançamento
    assert m["registered_expenses"] == "100.00"   # contada uma única vez


def test_assinatura_futura_projetada_sem_duplicar(user_a):
    with_history(user_a)
    card = user_a.post(f"{API}/cards", json={"nickname": "C", "closing_day": 10, "due_day": 17}).json()
    user_a.post(f"{API}/card-subscriptions", json={"card_id": card["id"], "description": "Streaming", "amount": "39.90",
                                                   "category_id": cat(user_a, "Assinaturas"), "charge_day": 5, "start_date": iso(CUR)})
    p = plan(user_a, total_amount="100.00", installments_count=3, first_installment_date=iso(CUR)).json()
    for m in analysis(user_a, p["id"])["months"]:
        assert D(m["card_installments"]) + D(m["subscriptions_projected"]) == D("39.90"), m["month"]


def test_orcamento_da_categoria_e_considerado(user_a):
    with_history(user_a)
    user_a.post(f"{API}/budgets", json={"category_id": cat(user_a, "Compras"), "month": iso(M1), "limit_amount": "100.00"})
    p = plan(user_a, total_amount="300.00", installments_count=1).json()
    m = analysis(user_a, p["id"])["months"][0]
    assert m["status"] == "attention" and any("orçamento definido" in f for f in m["factors"])


def test_simular_sem_salvar(user_a):
    with_history(user_a)
    body = {"name": "Tablet", "total_amount": "2600.00", "installments_count": 12, "first_installment_date": iso(M1),
            "category_id": cat(user_a, "Compras")}
    r = user_a.post(f"{API}/planned-purchases/simulate", json=body)
    assert r.status_code == 200 and len(r.json()["months"]) == 12
    assert user_a.get(f"{API}/planned-purchases").json() == []


# ------------------------------------------------------------ CRUD e validação

def test_editar_e_excluir(user_a):
    with_history(user_a)
    p = plan(user_a).json()
    r = user_a.patch(f"{API}/planned-purchases/{p['id']}", json={"installments_count": 10, "notes": "Esperar promoção"})
    assert r.status_code == 200 and r.json()["installment_amount"] == "260.00" and r.json()["notes"] == "Esperar promoção"
    assert len(analysis(user_a, p["id"])["months"]) == 10
    assert user_a.delete(f"{API}/planned-purchases/{p['id']}").status_code == 200
    assert user_a.get(f"{API}/planned-purchases/{p['id']}/analysis").status_code == 404


@pytest.mark.parametrize("over", [
    {"name": "  "}, {"total_amount": "0"}, {"total_amount": "-5.00"}, {"total_amount": "10.001"},
    {"installments_count": 0}, {"installments_count": 73}, {"first_installment_date": "31/12/2026"},
    {"category_id": "SALARIO"}, {"total_amount": "0.05", "installments_count": 12}, {"user_id": "x"},
])
def test_validacoes(user_a, over):
    if over.get("category_id") == "SALARIO":
        over["category_id"] = cat(user_a, "Salário")
    assert plan(user_a, **over).status_code == 422
    assert super_exec("SELECT count(*) FROM planned_purchases").scalar() == 0


# ------------------------------------------------------------ isolamento A x B

def test_isolamento(user_a, user_b):
    with_history(user_a)
    with_history(user_b, income="90000.00", variable="10.00")
    pb = plan(user_b, name="Compra do Bruno").json()
    pa = plan(user_a, total_amount="300.00", installments_count=1).json()
    assert [p["name"] for p in user_a.get(f"{API}/planned-purchases").json()] == ["Tablet"]
    m = analysis(user_a, pa["id"])["months"][0]
    assert (m["income"], m["other_planned"]) == ("5000.00", "0.00")  # nada de B entra na conta de A
    for method, path, body in [("GET", f"/planned-purchases/{pb['id']}/analysis", None),
                               ("PATCH", f"/planned-purchases/{pb['id']}", {"name": "hack"}),
                               ("DELETE", f"/planned-purchases/{pb['id']}", None)]:
        fn = {"GET": user_a.get, "PATCH": user_a.patch, "DELETE": user_a.delete}[method]
        r = fn(API + path, json=body) if body else fn(API + path)
        assert r.status_code == 404, path
    priv_b = user_b.post(f"{API}/categories", json={"name": "Privada B", "kind": "expense"}).json()["id"]
    assert plan(user_a, category_id=priv_b).status_code == 422
    assert user_b.get(f"{API}/planned-purchases").json()[0]["name"] == "Compra do Bruno"
    assert "Bruno" not in user_a.get(f"{API}/export/compras-planejadas.csv").content.decode("utf-8-sig")


def test_exclusao_da_conta_remove_compras_planejadas(user_a, user_b):
    plan(user_a)
    plan(user_b)
    assert user_a.delete(f"{API}/me", json={"password": PASSWORD, "confirmation": "EXCLUIR"}).status_code == 200
    assert super_exec("SELECT count(*) FROM planned_purchases").scalar() == 1
