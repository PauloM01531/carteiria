"""Regras puras de cartão: parcelas, centavos, competência, fechamento e status."""
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.services.calendar import add_months, clamp_day
from app.services.cards import split_installments, statement_dates, statement_status, suggest_reference_month

D = Decimal


def test_regra_fundamental_1200_em_12x():
    parts = split_installments(D("1200.00"), 12)
    assert parts == [D("100.00")] * 12
    assert sum(parts) == D("1200.00")


@pytest.mark.parametrize("total,n,expected_last", [
    ("100.00", 3, "33.34"),     # 33,33 + 33,33 + 33,34
    ("10.00", 3, "3.34"),
    ("0.05", 2, "0.03"),
    ("1000.01", 7, "142.91"),
    ("99.99", 1, "99.99"),
])
def test_diferenca_de_centavos_vai_para_a_ultima_parcela(total, n, expected_last):
    parts = split_installments(D(total), n)
    assert len(parts) == n
    assert sum(parts) == D(total)
    assert parts[-1] == D(expected_last)
    assert len(set(parts[:-1])) <= 1  # todas as anteriores iguais


def test_valor_pequeno_demais_para_as_parcelas():
    with pytest.raises(HTTPException):
        split_installments(D("0.05"), 6)


@pytest.mark.parametrize("closing,purchase,expected", [
    (10, date(2026, 10, 9), date(2026, 10, 1)),    # antes do fechamento: fatura de outubro
    (10, date(2026, 10, 10), date(2026, 11, 1)),   # no dia do fechamento: próxima fatura
    (10, date(2026, 10, 25), date(2026, 11, 1)),
    (31, date(2026, 2, 27), date(2026, 2, 1)),     # dia 31 em fevereiro fecha no dia 28
    (31, date(2026, 2, 28), date(2026, 3, 1)),
    (5, date(2026, 12, 20), date(2027, 1, 1)),     # virada de ano
])
def test_competencia_sugerida_pelo_fechamento(closing, purchase, expected):
    assert suggest_reference_month(closing, purchase) == expected


def test_datas_de_fechamento_e_vencimento():
    # Fecha dia 3 e vence dia 10: mesmo mês
    assert statement_dates(3, 10, date(2026, 11, 1)) == (date(2026, 11, 3), date(2026, 11, 10))
    # Fecha dia 25 e vence dia 5: vencimento no mês seguinte
    assert statement_dates(25, 5, date(2026, 12, 1)) == (date(2026, 12, 25), date(2027, 1, 5))
    # Dia 31 ajustado ao tamanho do mês
    assert statement_dates(31, 31, date(2026, 4, 1))[0] == date(2026, 4, 30)


def test_status_da_fatura():
    c, d = date(2026, 11, 3), date(2026, 11, 10)
    assert statement_status(D("100"), D("0"), c, d, date(2026, 11, 1)) == "open"
    assert statement_status(D("100"), D("0"), c, d, date(2026, 11, 5)) == "closed"
    assert statement_status(D("100"), D("40"), c, d, date(2026, 11, 5)) == "partial"
    assert statement_status(D("100"), D("100"), c, d, date(2026, 11, 20)) == "paid"
    assert statement_status(D("100"), D("40"), c, d, date(2026, 11, 11)) == "overdue"
    assert statement_status(D("0"), D("0"), c, d, date(2026, 11, 11)) == "empty"


def test_aritmetica_de_meses():
    assert add_months(date(2026, 11, 1), 2) == date(2027, 1, 1)
    assert add_months(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert clamp_day(2028, 2, 30) == date(2028, 2, 29)
