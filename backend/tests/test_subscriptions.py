"""Assinaturas recorrentes no cartão: geração mensal, faturas, alterações, cancelamento e isolamento A x B."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import get_app_engine
from app.services.calendar import add_months, first_of_month, today
from app.services.subscriptions import charge_dates
from tests.conftest import PASSWORD, owner_exec, super_exec

API = "/api/v1"


def cat(client, name):
    return next(c["id"] for c in client.get(f"{API}/categories").json() if c["name"] == name)


def new_card(client, **over):
    body = {"nickname": "Nubank", "closing_day": 10, "due_day": 17, **over}
    r = client.post(f"{API}/cards", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def new_sub(client, card_id, **over):
    body = {"card_id": card_id, "description": "Streaming", "amount": "39.90", "category_id": cat(client, "Assinaturas"),
            "charge_day": 5, "start_date": iso(add_months(first_of_month(today()), -2))}
    body.update(over)
    return client.post(f"{API}/card-subscriptions", json=body)


def iso(d: date) -> str:
    return d.isoformat()


def charges(client, card_id=None):
    params = {"card_id": card_id} if card_id else {}
    return sorted([p for p in client.get(f"{API}/card-purchases", params=params).json() if p["subscription_id"]],
                  key=lambda p: p["purchase_date"])


# ------------------------------------------------------------ calendário

def _sub(**kw):
    return SimpleNamespace(**{"charge_day": 5, "start_date": date(2026, 1, 1), "end_date": None, **kw})


def test_datas_de_cobranca():
    assert charge_dates(_sub(), date(2026, 3, 31)) == [date(2026, 1, 5), date(2026, 2, 5), date(2026, 3, 5)]
    assert charge_dates(_sub(start_date=date(2026, 1, 10)), date(2026, 3, 31)) == [date(2026, 2, 5), date(2026, 3, 5)]
    assert charge_dates(_sub(charge_day=31), date(2026, 2, 28)) == [date(2026, 1, 31), date(2026, 2, 28)]
    assert charge_dates(_sub(end_date=date(2026, 2, 5)), date(2026, 12, 31)) == [date(2026, 1, 5), date(2026, 2, 5)]


# ------------------------------------------------------------ geração

def test_assinatura_gera_uma_cobranca_por_mes_na_fatura_certa(user_a):
    card = new_card(user_a)
    r = new_sub(user_a, card["id"])
    assert r.status_code == 201, r.text
    sub = r.json()
    assert sub["next_charge"] is not None

    cs = charges(user_a)
    # Do início (há 2 meses) até ~1 mês à frente: uma cobrança por mês, todas de R$ 39,90
    expected = charge_dates(SimpleNamespace(charge_day=5, start_date=add_months(first_of_month(today()), -2), end_date=None),
                            today() + timedelta(days=31))
    assert [c["purchase_date"] for c in cs] == [iso(d) for d in expected]
    assert all(c["total_amount"] == "39.90" and c["installments_count"] == 1 for c in cs)
    # Dia 5 é antes do fechamento (10): cada cobrança entra na fatura do próprio mês
    assert all(c["first_statement_month"] == c["purchase_date"][:8] + "01" for c in cs)
    # Cada fatura recebe só a sua cobrança, marcada como assinatura
    st = user_a.get(f"{API}/statements", params={"card_id": card["id"]}).json()
    assert all(s["total"] == "39.90" for s in st)
    item = user_a.get(f"{API}/statements/{st[0]['id']}").json()["items"][0]
    assert item["is_subscription"] is True and item["description"] == "Streaming"


def test_consultar_varias_vezes_nao_duplica(user_a):
    card = new_card(user_a)
    new_sub(user_a, card["id"])
    n = len(charges(user_a))
    for _ in range(3):
        user_a.get(f"{API}/statements")
        user_a.get(f"{API}/dashboard")
        user_a.get(f"{API}/reports/summary")
    assert len(charges(user_a)) == n
    assert super_exec("SELECT count(*) FROM card_purchases").scalar() == n


def test_entra_nos_relatorios_e_no_limite(user_a):
    card = new_card(user_a, credit_limit="1000.00")
    new_sub(user_a, card["id"], start_date=iso(first_of_month(today())), charge_day=1)
    s = user_a.get(f"{API}/reports/summary", params={"month": iso(today())}).json()
    assert s["expense"] == "39.90" and s["top_category"]["category_name"] == "Assinaturas"
    assert user_a.get(f"{API}/cards/{card['id']}").json()["used_amount"] in ("39.90", "79.80")


def test_alterar_valor_muda_so_as_cobrancas_futuras(user_a):
    card = new_card(user_a)
    sub = new_sub(user_a, card["id"]).json()
    before = charges(user_a)
    r = user_a.patch(f"{API}/card-subscriptions/{sub['id']}", json={"amount": "44.90"})
    assert r.status_code == 200 and r.json()["amount"] == "44.90"
    after = charges(user_a)
    assert len(after) == len(before)
    for c in after:
        expected = "44.90" if c["purchase_date"] > iso(today()) else "39.90"
        assert c["total_amount"] == expected, c


def test_pausar_e_cancelar(user_a):
    card = new_card(user_a)
    sub = new_sub(user_a, card["id"]).json()
    past = [c for c in charges(user_a) if c["purchase_date"] <= iso(today())]
    r = user_a.patch(f"{API}/card-subscriptions/{sub['id']}", json={"active": False})
    assert r.status_code == 200 and r.json()["next_charge"] is None
    assert charges(user_a) == past  # futuras removidas, histórico mantido
    user_a.patch(f"{API}/card-subscriptions/{sub['id']}", json={"active": True})
    assert len(charges(user_a)) >= len(past)
    assert user_a.delete(f"{API}/card-subscriptions/{sub['id']}").status_code == 200
    remaining = user_a.get(f"{API}/card-purchases").json()
    assert {c["purchase_date"] for c in remaining} == {c["purchase_date"] for c in past}
    assert all(c["subscription_id"] is None for c in remaining)


def test_data_final_limita_as_cobrancas(user_a):
    card = new_card(user_a)
    start = add_months(first_of_month(today()), -3)
    new_sub(user_a, card["id"], start_date=iso(start), end_date=iso(start + timedelta(days=40)))
    assert len(charges(user_a)) == 2


def test_cobranca_gerada_nao_pode_ser_apagada_diretamente_mas_pode_ter_valor_ajustado(user_a):
    card = new_card(user_a)
    new_sub(user_a, card["id"])
    all_charges = charges(user_a)
    c = all_charges[0]
    r = user_a.delete(f"{API}/card-purchases/{c['id']}")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "subscription_charge"
    r = user_a.patch(f"{API}/card-purchases/{c['id']}", json={"total_amount": "19.95"})
    assert r.status_code == 200 and r.json()["total_amount"] == "19.95"
    assert len(charges(user_a)) == len(all_charges)  # o ajuste não gera duplicata


def test_cobranca_em_fatura_paga_nao_e_removida(user_a):
    card = new_card(user_a)
    # Uma única cobrança, daqui a 3 dias (ainda futura)
    sub = new_sub(user_a, card["id"], start_date=iso(today() + timedelta(days=1)),
                  charge_day=(today() + timedelta(days=3)).day).json()
    future = charges(user_a)
    assert len(future) == 1 and future[0]["purchase_date"] > iso(today())
    st = user_a.get(f"{API}/statements").json()[-1]
    user_a.post(f"{API}/statements/{st['id']}/payments", json={"amount": "39.90", "paid_on": iso(today())})
    assert user_a.delete(f"{API}/card-subscriptions/{sub['id']}").status_code == 200
    assert len(user_a.get(f"{API}/card-purchases").json()) == len(future)


@pytest.mark.parametrize("over", [{"amount": "0"}, {"charge_day": 0}, {"charge_day": 32}, {"description": " "},
                                  {"category_id": "SALARIO"}, {"end_date": "2000-01-01"}, {"user_id": "x"}])
def test_validacoes(user_a, over):
    card = new_card(user_a)
    if over.get("category_id") == "SALARIO":
        over["category_id"] = cat(user_a, "Salário")
    assert new_sub(user_a, card["id"], **over).status_code == 422


def test_cartao_inativo_nao_gera(user_a):
    card = new_card(user_a)
    user_a.patch(f"{API}/cards/{card['id']}", json={"active": False})
    assert new_sub(user_a, card["id"]).status_code == 422


# ------------------------------------------------------------ isolamento A x B

def test_isolamento_de_assinaturas(user_a, user_b):
    card_b = new_card(user_b, nickname="Cartão do Bruno")
    sub_b = new_sub(user_b, card_b["id"], description="Streaming do Bruno").json()
    assert user_a.get(f"{API}/card-subscriptions").json() == []
    assert user_a.get(f"{API}/card-subscriptions", params={"card_id": card_b["id"]}).json() == []
    assert user_a.patch(f"{API}/card-subscriptions/{sub_b['id']}", json={"amount": "1.00"}).status_code == 404
    assert user_a.delete(f"{API}/card-subscriptions/{sub_b['id']}").status_code == 404
    # A não cria assinatura no cartão de B nem move a sua para lá
    assert new_sub(user_a, card_b["id"]).status_code == 404
    card_a = new_card(user_a)
    sub_a = new_sub(user_a, card_a["id"]).json()
    assert user_a.patch(f"{API}/card-subscriptions/{sub_a['id']}", json={"card_id": card_b["id"]}).status_code == 404
    # As cobranças de B não aparecem para A e as de B continuam intactas
    assert "Bruno" not in user_a.get(f"{API}/card-purchases").text
    assert all(c["total_amount"] == "39.90" for c in charges(user_b))
    assert user_b.get(f"{API}/card-subscriptions").json()[0]["description"] == "Streaming do Bruno"


def test_rls_e_gatilho_no_banco(user_a, user_b):
    card_b = new_card(user_b)
    sub_b = new_sub(user_b, card_b["id"]).json()
    a = owner_exec("SELECT id FROM users WHERE email='ana@exemplo.com.br'").scalar()
    with get_app_engine().begin() as conn:
        conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(a)})
        assert conn.execute(text("SELECT count(*) FROM card_subscriptions")).scalar() == 0
    card_a = new_card(user_a)
    alim = cat(user_a, "Compras")
    with pytest.raises(DBAPIError, match="outro usuario"):
        with get_app_engine().begin() as conn:
            conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(a)})
            conn.execute(text("""INSERT INTO card_purchases (user_id, card_id, description, total_amount, purchase_date,
                                 category_id, installments_count, first_statement_month, subscription_id)
                                 VALUES (:a, :c, 'x', 1, '2026-10-01', :cat, 1, '2026-10-01', :s)"""),
                         {"a": str(a), "c": card_a["id"], "cat": alim, "s": sub_b["id"]})


def test_exclusao_da_conta_remove_assinaturas(user_a, user_b):
    new_sub(user_a, new_card(user_a)["id"])
    new_sub(user_b, new_card(user_b)["id"])
    assert user_a.delete(f"{API}/me", json={"password": PASSWORD, "confirmation": "EXCLUIR"}).status_code == 200
    assert super_exec("SELECT count(*) FROM card_subscriptions").scalar() == 1
    assert len(user_b.get(f"{API}/card-subscriptions").json()) == 1
