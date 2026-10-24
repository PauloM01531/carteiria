"""Relatórios, comparativos e painel. Endpoints documentados (/api/docs) e reutilizáveis pela futura IA:
todos dependem da sessão autenticada; nenhum aceita user_id."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app.db import get_db
from app.models import CardStatement
from app.schemas_reports import (
    Basis,
    CategoryShare,
    CommitmentsOut,
    CompareOut,
    DashboardOut,
    MonthPoint,
    RecentTx,
    SummaryOut,
)
from app.services import planning, reports
from app.services.cards import totals_for
from app.services.calendar import add_months, first_of_month, today

router = APIRouter(prefix="/reports", tags=["relatórios"])
dash = APIRouter(tags=["painel"])


def _filters(
    start: date | None = Query(default=None, description="Data inicial (padrão: 1º dia do mês atual)"),
    end: date | None = Query(default=None, description="Data final (padrão: último dia do mês atual)"),
    month: date | None = Query(default=None, description="Atalho: qualquer data do mês desejado"),
    year: int | None = Query(default=None, ge=2000, le=2100, description="Atalho: ano inteiro"),
    basis: Basis = "competencia",
    category_id: uuid.UUID | None = None,
    card_id: uuid.UUID | None = None,
    kind: str | None = Query(default=None, pattern="^(income|expense)$"),
) -> reports.Filters:
    if month:
        start, end = first_of_month(month), reports.month_end(first_of_month(month))
    elif year:
        start, end = date(year, 1, 1), date(year, 12, 31)
    else:
        cur = first_of_month(today())
        start, end = start or cur, end or reports.month_end(cur)
    if start > end or (end - start).days > 3700:
        raise HTTPException(422, {"code": "invalid_period", "message": "Período inválido (máximo de 10 anos)."})
    return reports.Filters(start, end, basis, category_id, card_id, kind)  # type: ignore[arg-type]


@router.get("/summary", response_model=SummaryOut, summary="Quanto entrou, quanto saiu, maior despesa e categoria líder")
def summary(f: reports.Filters = Depends(_filters), ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return reports.summary(db, ctx.user.id, f)


@router.get("/categories", response_model=list[CategoryShare], summary="Distribuição por categoria")
def categories(f: reports.Filters = Depends(_filters), ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return reports.by_category(db, ctx.user.id, f, kind=f.kind or "expense")


@router.get("/monthly", response_model=list[MonthPoint], summary="Série mensal de receitas, despesas e saldo")
def monthly(
    end_month: date | None = None,
    months: int = Query(default=12, ge=1, le=36),
    basis: Basis = "competencia",
    category_id: uuid.UUID | None = None,
    card_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    return reports.monthly(db, ctx.user.id, end_month or today(), months, basis, category_id, card_id)


@router.get("/compare", response_model=CompareOut, summary="Compara dois meses (diferença absoluta e percentual)")
def compare(
    month_b: date | None = Query(default=None, description="Mês atual (padrão: mês corrente)"),
    month_a: date | None = Query(default=None, description="Mês de comparação (padrão: mês anterior a month_b)"),
    basis: Basis = "competencia",
    category_id: uuid.UUID | None = None,
    card_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    b = first_of_month(month_b or today())
    a = first_of_month(month_a) if month_a else add_months(b, -1)
    return reports.compare(db, ctx.user.id, a, b, basis, category_id, card_id)


@router.get("/commitments", response_model=CommitmentsOut, summary="Faturas em aberto, parcelas futuras e contas previstas")
def commitments(horizon_days: int = Query(default=30, ge=1, le=400), ctx: AuthContext = Depends(get_auth),
                db: Session = Depends(get_db)):
    out = reports.commitments(db, ctx.user.id, horizon_days=horizon_days)
    db.commit()
    return out


@dash.get("/dashboard", response_model=DashboardOut, summary="Todos os indicadores do painel de um mês")
def dashboard(month: date | None = None, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    uid = ctx.user.id
    m = first_of_month(month or today())
    period = reports.Filters(m, reports.month_end(m))
    prev = add_months(m, -1)
    s = reports.summary(db, uid, period)
    ps = reports.summary(db, uid, reports.Filters(prev, reports.month_end(prev)))
    com = reports.commitments(db, uid)
    cash = reports.cash_balance(db, uid, min(reports.month_end(m), today()))
    st_ids = list(db.scalars(select(CardStatement.id).where(CardStatement.user_id == uid, CardStatement.reference_month == m)))
    month_statements = sum((t.total for t in totals_for(db, uid, st_ids).values()), reports.ZERO)
    out = {
        "month": m,
        "summary": s,
        "previous_summary": ps,
        "expense_change_pct": reports.pct_change(ps["expense"], s["expense"]),
        "cash_balance": cash,
        # Saldo calculado não é dinheiro disponível: descontamos o que já está comprometido.
        "balance_after_commitments": cash - com["total"],
        "month_statements_total": reports.q(month_statements),
        "commitments": com,
        "monthly": reports.monthly(db, uid, m, 12, "competencia"),
        "categories": reports.by_category(db, uid, period),
        "budgets": planning.budgets_for_month(db, uid, m),
        "recent": [RecentTx(**r) for r in reports.recent_transactions(db, uid)],
    }
    db.commit()
    return out
