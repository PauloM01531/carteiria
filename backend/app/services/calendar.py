"""Datas de referência no fuso America/Fortaleza e aritmética de meses."""
import calendar
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Fortaleza")


def today() -> date:
    return datetime.now(TZ).date()


def first_of_month(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, months: int) -> date:
    """Primeiro dia do mês deslocado."""
    idx = d.year * 12 + (d.month - 1) + months
    return date(idx // 12, idx % 12 + 1, 1)


def clamp_day(year: int, month: int, day: int) -> date:
    """Dia 31 em fevereiro vira 28/29; dia 31 em abril vira 30."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))
