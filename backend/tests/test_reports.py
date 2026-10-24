"""Relatórios, comparativos, painel, orçamentos, metas e exportação — cálculos e isolamento A x B."""
import csv
import io
import zipfile
from decimal import Decimal

import pytest

from app.services.reports import pct_change
from tests.conftest import PASSWORD

API = "/api/v1"
D = Decimal


def cat(client, name):
    return next(c["id"] for c in client.get(f"{API}/categories", params={"include_inactive": "true"}).json() if c["name"] == name)


def tx(client, kind, amount, day, category, desc="x", status="settled"):
    r = client.post(f"{API}/transactions", json={"kind": kind, "description": desc, "amount": amount, "occurred_on": day,
                                                  "category_id": cat(client, category), "payment_method": "pix", "status": status})
    assert r.status_code == 201, r.text
    return r.json()


def card_with_purchase(client, total="1200.00", n=12, day="2026-09-05", first="2026-09-01", category="Compras", desc="Notebook"):
    c = client.post(f"{API}/cards", json={"nickname": "Cartão", "closing_day": 10, "due_day": 17}).json()
    r = client.post(f"{API}/card-purchases", json={"card_id": c["id"], "description": desc, "total_amount": total,
                                                    "purchase_date": day, "category_id": cat(client, category),
                                                    "installments_count": n, "first_statement_month": first})
    assert r.status_code == 201, r.text
    return c, r.json()


# ------------------------------------------------------------ percentuais

@pytest.mark.parametrize("prev,cur,expected", [
    ("100", "150", "50.0"), ("200", "150", "-25.0"), ("100", "100", "0.0"), ("3", "4", "33.3"), ("0", "50", None),
])
def test_variacao_percentual(prev, cur, expected):
    r = pct_change(D(prev), D(cur))
    assert (str(r) if r is not None else None) == expected


# ------------------------------------------------------------ resumo e bases de cálculo

def test_resumo_do_mes_responde_as_perguntas(user_a):
    tx(user_a, "income", "5000.00", "2026-10-05", "Salário")
    tx(user_a, "expense", "450.00", "2026-10-06", "Alimentação", "Mercado")
    tx(user_a, "expense", "1500.00", "2026-10-07", "Moradia", "Aluguel")
    tx(user_a, "expense", "80.00", "2026-09-10", "Alimentação")  # outro mês
    s = user_a.get(f"{API}/reports/summary", params={"month": "2026-10-15"}).json()
    assert (s["income"], s["expense"], s["balance"]) == ("5000.00", "1950.00", "3050.00")   # quanto gastei / economizei
    assert s["largest_expense"]["description"] == "Aluguel"                                 # maior despesa
    assert s["top_category"]["category_name"] == "Moradia"                                  # categoria que mais consumiu
    assert s["savings_rate"] == "61.0"
    ali = user_a.get(f"{API}/reports/summary", params={"month": "2026-10-01", "category_id": cat(user_a, "Alimentação")}).json()
    assert ali["expense"] == "450.00"                                                       # quanto gastei com alimentação


def test_parcelas_entram_por_competencia_sem_duplicar(user_a):
    # Compra de 1.200 em 12x a partir de setembro: R$ 100 por mês, nunca R$ 1.200 em um mês
    card, _purchase = card_with_purchase(user_a)
    tx(user_a, "expense", "50.00", "2026-10-03", "Alimentação")
    comp = user_a.get(f"{API}/reports/summary", params={"month": "2026-10-01"}).json()
    assert comp["expense"] == "150.00"
    # Base "data da compra": a compra inteira cai no mês em que foi feita
    lanc_set = user_a.get(f"{API}/reports/summary", params={"month": "2026-09-01", "basis": "lancamento"}).json()
    lanc_out = user_a.get(f"{API}/reports/summary", params={"month": "2026-10-01", "basis": "lancamento"}).json()
    assert (lanc_set["expense"], lanc_out["expense"]) == ("1200.00", "50.00")
    # Base "caixa": só o que foi pago (pagamento da fatura de setembro em outubro)
    st = user_a.get(f"{API}/statements").json()[0]
    user_a.post(f"{API}/statements/{st['id']}/payments", json={"amount": "100.00", "paid_on": "2026-10-10"})
    caixa = user_a.get(f"{API}/reports/summary", params={"month": "2026-10-01", "basis": "caixa"}).json()
    assert caixa["expense"] == "150.00"  # 50 do mercado + 100 do pagamento da fatura
    # O pagamento da fatura não altera a base competência (sem dupla contagem)
    assert user_a.get(f"{API}/reports/summary", params={"month": "2026-10-01"}).json()["expense"] == "150.00"
    # Filtro por cartão considera só as parcelas daquele cartão
    by_card = user_a.get(f"{API}/reports/summary", params={"month": "2026-10-01", "card_id": card["id"]}).json()
    assert by_card["expense"] == "100.00"


def test_comparacao_entre_meses(user_a):
    tx(user_a, "expense", "200.00", "2026-09-10", "Alimentação")
    tx(user_a, "expense", "300.00", "2026-10-10", "Alimentação")
    tx(user_a, "expense", "100.00", "2026-10-11", "Lazer")
    c = user_a.get(f"{API}/reports/compare", params={"month_a": "2026-09-01", "month_b": "2026-10-01"}).json()
    assert c["expense"] == {"previous": "200.00", "current": "400.00", "diff": "200.00", "pct": "100.0"}
    lazer = next(x for x in c["categories"] if x["category_name"] == "Lazer")
    assert lazer["pct"] is None and lazer["diff"] == "100.00"   # anterior zero: sem percentual
    vazio = user_a.get(f"{API}/reports/compare", params={"month_a": "2020-01-01", "month_b": "2020-02-01"}).json()
    assert vazio["expense"]["pct"] is None and vazio["expense"]["diff"] == "0.00"


def test_serie_mensal_e_saldo_acumulado(user_a):
    tx(user_a, "income", "1000.00", "2026-08-05", "Salário")
    tx(user_a, "expense", "400.00", "2026-08-10", "Moradia")
    tx(user_a, "income", "1000.00", "2026-10-05", "Salário")
    s = user_a.get(f"{API}/reports/monthly", params={"end_month": "2026-10-01", "months": 3}).json()
    assert [p["month"] for p in s] == ["2026-08-01", "2026-09-01", "2026-10-01"]
    assert [p["balance"] for p in s] == ["600.00", "0.00", "1000.00"]
    assert [p["cumulative"] for p in s] == ["600.00", "600.00", "1600.00"]


def test_compromissos_futuros_e_saldo_disponivel(user_a):
    tx(user_a, "income", "3000.00", "2026-10-01", "Salário")
    card_with_purchase(user_a, total="1200.00", n=12, first="2026-11-01")
    user_a.post(f"{API}/bills", json={"name": "Internet", "amount_type": "fixed", "expected_amount": "100.00",
                                      "category_id": cat(user_a, "Internet"), "due_day": 28, "start_date": "2026-10-01"})
    c = user_a.get(f"{API}/reports/commitments").json()
    assert c["future_installments_total"] == "1200.00"  # todas as parcelas são de competências futuras
    assert c["open_statements_total"] == "1200.00"
    assert len(c["future_installments_by_month"]) == 12
    d = user_a.get(f"{API}/dashboard", params={"month": "2026-10-01"}).json()
    # Saldo calculado (3.000) não é o mesmo que dinheiro disponível após compromissos
    assert d["cash_balance"] == "3000.00"
    assert D(d["balance_after_commitments"]) < D(d["cash_balance"])
    assert D(d["balance_after_commitments"]) == D("3000.00") - D(d["commitments"]["total"])


def test_painel_vazio_tem_valores_zerados(user_a):
    d = user_a.get(f"{API}/dashboard").json()
    assert d["summary"]["income"] == d["summary"]["expense"] == d["cash_balance"] == "0.00"
    assert d["categories"] == [] and d["recent"] == [] and d["budgets"] == []
    assert len(d["monthly"]) == 12 and all(p["expense"] == "0.00" for p in d["monthly"])


# ------------------------------------------------------------ orçamentos

def test_orcamento_alertas_e_comparacao(user_a):
    alim = cat(user_a, "Alimentação")
    r = user_a.post(f"{API}/budgets", json={"category_id": alim, "month": "2026-10-20", "limit_amount": "500.00"})
    assert r.status_code == 201 and r.json()["month"] == "2026-10-01"
    b = r.json()
    assert (b["spent"], b["remaining"], b["percent"], b["status"]) == ("0.00", "500.00", "0.0", "ok")
    tx(user_a, "expense", "420.00", "2026-10-05", "Alimentação")
    b = user_a.get(f"{API}/budgets", params={"month": "2026-10-01"}).json()[0]
    assert (b["percent"], b["status"]) == ("84.0", "warning")          # perto do limite
    card_with_purchase(user_a, total="100.00", n=1, day="2026-10-02", first="2026-10-01", category="Alimentação")
    b = user_a.get(f"{API}/budgets", params={"month": "2026-10-01"}).json()[0]
    assert (b["spent"], b["remaining"], b["status"]) == ("520.00", "-20.00", "over")   # ultrapassado (parcela conta)
    tx(user_a, "expense", "300.00", "2026-09-05", "Alimentação")
    b = user_a.get(f"{API}/budgets", params={"month": "2026-10-01"}).json()[0]
    assert b["previous_months"][0] == {"month": "2026-09-01", "spent": "300.00"}
    # Duplicado e categoria de receita são recusados
    assert user_a.post(f"{API}/budgets", json={"category_id": alim, "month": "2026-10-01", "limit_amount": "1.00"}).status_code == 409
    assert user_a.post(f"{API}/budgets", json={"category_id": cat(user_a, "Salário"), "month": "2026-10-01",
                                                "limit_amount": "1.00"}).status_code == 422
    # Copiar para o mês seguinte
    assert "1 orçamento" in user_a.post(f"{API}/budgets/copy", json={"source_month": "2026-10-01", "target_month": "2026-11-01"}).json()["message"]
    assert len(user_a.get(f"{API}/budgets", params={"month": "2026-11-01"}).json()) == 1
    # Aparece no painel
    assert user_a.get(f"{API}/dashboard", params={"month": "2026-10-01"}).json()["budgets"][0]["status"] == "over"


# ------------------------------------------------------------ metas

def test_metas_progresso_e_aportes(user_a):
    g = user_a.post(f"{API}/goals", json={"name": "Reserva", "target_amount": "1000.00", "deadline": "2027-04-30"}).json()
    assert g["percent"] == "0.0" and g["status"] == "in_progress"
    g = user_a.post(f"{API}/goals/{g['id']}/contributions", json={"amount": "250.00", "contributed_on": "2026-10-01"}).json()
    assert (g["saved"], g["remaining"], g["percent"]) == ("250.00", "750.00", "25.0")
    assert g["monthly_needed"] is not None
    assert user_a.post(f"{API}/goals/{g['id']}/contributions", json={"amount": "-300.00", "contributed_on": "2026-10-02"}).status_code == 422
    g = user_a.post(f"{API}/goals/{g['id']}/contributions", json={"amount": "-50.00", "contributed_on": "2026-10-02"}).json()
    assert g["saved"] == "200.00"
    g = user_a.post(f"{API}/goals/{g['id']}/contributions", json={"amount": "800.00", "contributed_on": "2026-10-03"}).json()
    assert g["status"] == "achieved" and g["percent"] == "100.0"
    first = g["contributions"][0]["id"]
    g = user_a.delete(f"{API}/goals/{g['id']}/contributions/{first}").json()
    assert g["saved"] == "750.00"


# ------------------------------------------------------------ exportação

def _csv(resp):
    text = resp.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text), delimiter=";"))


def test_exportacao_csv_formato_brasileiro_e_protecao_contra_formulas(user_a):
    tx(user_a, "expense", "1234.56", "2026-10-05", "Alimentação", "=HYPERLINK(\"http://mal\")")
    r = user_a.get(f"{API}/export/lancamentos.csv")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"\xef\xbb\xbf")
    rows = _csv(r)
    assert rows[0][:4] == ["Data", "Tipo", "Descrição", "Valor"]
    assert rows[1][0] == "05/10/2026" and rows[1][3] == "1234,56"
    assert rows[1][2].startswith("'=")   # fórmula neutralizada
    assert user_a.get(f"{API}/export/senhas.csv").status_code == 404


def test_exportacoes_contem_somente_dados_do_usuario(user_a, user_b):
    tx(user_a, "expense", "10.00", "2026-10-05", "Alimentação", "Gasto da Ana")
    tx(user_b, "expense", "20.00", "2026-10-05", "Alimentação", "Gasto do Bruno")
    card_with_purchase(user_b, desc="Compra do Bruno")
    user_b.post(f"{API}/goals", json={"name": "Meta do Bruno", "target_amount": "10.00"})
    for ds in ["lancamentos", "compras-cartao", "parcelas", "cartoes", "metas", "orcamentos", "contas-recorrentes",
               "pagamentos-fatura", "categorias"]:
        assert "Bruno" not in user_a.get(f"{API}/export/{ds}.csv").content.decode("utf-8-sig"), ds
    z = zipfile.ZipFile(io.BytesIO(user_a.get(f"{API}/export/all.zip").content))
    everything = "".join(z.read(n).decode("utf-8-sig") for n in z.namelist())
    assert "Gasto da Ana" in everything and "Bruno" not in everything
    assert "argon2" not in everything and "ana@exemplo.com.br" in z.read("perfil.json").decode()


def test_relatorios_e_painel_isolados(user_a, user_b):
    tx(user_b, "income", "9999.00", "2026-10-05", "Salário")
    tx(user_b, "expense", "777.00", "2026-10-06", "Lazer", "Viagem do Bruno")
    card_with_purchase(user_b)
    alim = cat(user_b, "Alimentação")
    user_b.post(f"{API}/budgets", json={"category_id": alim, "month": "2026-10-01", "limit_amount": "100.00"})
    user_b.post(f"{API}/goals", json={"name": "Carro do Bruno", "target_amount": "50000.00"})

    s = user_a.get(f"{API}/reports/summary", params={"month": "2026-10-01"}).json()
    assert (s["income"], s["expense"], s["largest_expense"]) == ("0.00", "0.00", None)
    for basis in ("competencia", "lancamento", "caixa"):
        assert user_a.get(f"{API}/reports/summary", params={"year": 2026, "basis": basis}).json()["expense"] == "0.00"
    assert user_a.get(f"{API}/reports/categories", params={"year": 2026}).json() == []
    assert all(p["income"] == "0.00" for p in user_a.get(f"{API}/reports/monthly").json())
    assert user_a.get(f"{API}/reports/commitments").json()["total"] == "0.00"
    d = user_a.get(f"{API}/dashboard", params={"month": "2026-10-01"}).json()
    assert d["recent"] == [] and d["budgets"] == [] and d["cash_balance"] == "0.00"
    assert user_a.get(f"{API}/budgets", params={"month": "2026-10-01"}).json() == []
    assert user_a.get(f"{API}/goals").json() == []
    # Filtrar pelo cartão ou categoria de B não revela nada
    card_b = user_b.get(f"{API}/cards").json()[0]["id"]
    assert user_a.get(f"{API}/reports/summary", params={"year": 2026, "card_id": card_b}).json()["expense"] == "0.00"
    # IDs de B na URL
    bud_b = user_b.get(f"{API}/budgets", params={"month": "2026-10-01"}).json()[0]["id"]
    goal_b = user_b.get(f"{API}/goals").json()[0]["id"]
    assert user_a.patch(f"{API}/budgets/{bud_b}", json={"limit_amount": "1.00"}).status_code == 404
    assert user_a.delete(f"{API}/budgets/{bud_b}").status_code == 404
    assert user_a.patch(f"{API}/goals/{goal_b}", json={"name": "x"}).status_code == 404
    assert user_a.delete(f"{API}/goals/{goal_b}").status_code == 404
    assert user_a.post(f"{API}/goals/{goal_b}/contributions", json={"amount": "1.00", "contributed_on": "2026-10-01"}).status_code == 404
    # A não cria orçamento com categoria privada de B
    priv_b = user_b.post(f"{API}/categories", json={"name": "Privada B", "kind": "expense"}).json()["id"]
    assert user_a.post(f"{API}/budgets", json={"category_id": priv_b, "month": "2026-10-01", "limit_amount": "1.00"}).status_code == 422
    # Dados de B continuam intactos
    assert user_b.get(f"{API}/reports/summary", params={"month": "2026-10-01"}).json()["income"] == "9999.00"


def test_exclusao_da_conta_remove_orcamentos_e_metas(user_a, user_b):
    user_a.post(f"{API}/goals", json={"name": "Meta A", "target_amount": "10.00"})
    user_b.post(f"{API}/goals", json={"name": "Meta B", "target_amount": "10.00"})
    assert user_a.delete(f"{API}/me", json={"password": PASSWORD, "confirmation": "EXCLUIR"}).status_code == 200
    assert [g["name"] for g in user_b.get(f"{API}/goals").json()] == ["Meta B"]
