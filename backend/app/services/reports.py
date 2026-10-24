"""Relatórios e indicadores financeiros. Funções controladas e reutilizáveis (inclusive pela futura IA).

Toda função recebe o `user_id` da sessão autenticada e filtra por ele; o RLS é a segunda camada.

Bases de cálculo das despesas (evitam contar o mesmo gasto duas vezes):
- "competencia" (padrão): lançamentos pela data + parcelas de cartão pelo mês da fatura.
- "lancamento": lançamentos pela data + compras de cartão pelo valor total na data da compra.
- "caixa": somente o que saiu de fato: lançamentos pagos + pagamentos de fatura pela data do pagamento.
Receitas são sempre os lançamentos de receita pela data (na base "caixa", só os recebidos).
"""
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BillOccurrence,
    CardPurchase,
    CardStatement,
    Category,
    Installment,
    StatementPayment,
    Transaction,
)
from app.services.calendar import add_months, first_of_month, today

Basis = Literal["competencia", "lancamento", "caixa"]
ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def q(v) -> Decimal:
    return Decimal(v or 0).quantize(CENT)


def month_end(month: date) -> date:
    return add_months(month, 1) - timedelta(days=1)


def pct_change(previous: Decimal, current: Decimal) -> Decimal | None:
    """Variação percentual. Sem base (anterior = 0) retorna None em vez de dividir por zero."""
    if previous == 0:
        return None
    return ((current - previous) / previous * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


@dataclass
class Filters:
    start: date
    end: date
    basis: Basis = "competencia"
    category_id: uuid.UUID | None = None
    card_id: uuid.UUID | None = None
    kind: Literal["income", "expense"] | None = None


@dataclass
class Line:
    """Um valor que compõe a despesa/receita do período, de qualquer origem."""
    source: str           # transaction | installment | purchase | statement_payment
    kind: str             # income | expense
    amount: Decimal
    day: date
    description: str
    category_id: uuid.UUID | None
    category_name: str
    card_id: uuid.UUID | None = None
    extra: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- coleta das linhas

def lines(db: Session, user_id: uuid.UUID, f: Filters) -> list[Line]:
    out: list[Line] = []
    want_income = f.kind in (None, "income")
    want_expense = f.kind in (None, "expense")

    # Lançamentos (receitas e despesas). Filtrar por cartão exclui lançamentos avulsos.
    if f.card_id is None:
        stmt = (
            select(Transaction, Category.name)
            .join(Category, Category.id == Transaction.category_id)
            .where(Transaction.user_id == user_id, Transaction.occurred_on >= f.start, Transaction.occurred_on <= f.end)
        )
        if f.basis == "caixa":
            stmt = stmt.where(Transaction.status == "settled")
        if f.category_id:
            stmt = stmt.where(Transaction.category_id == f.category_id)
        for tx, cname in db.execute(stmt).all():
            if (tx.kind == "income" and want_income) or (tx.kind == "expense" and want_expense):
                out.append(Line("transaction", tx.kind, tx.amount, tx.occurred_on, tx.description, tx.category_id, cname,
                                extra={"status": tx.status, "id": str(tx.id)}))

    if not want_expense:
        return out

    if f.basis == "competencia":
        stmt = (
            select(Installment, CardPurchase, CardStatement.reference_month, Category.name)
            .join(CardPurchase, CardPurchase.id == Installment.purchase_id)
            .join(CardStatement, CardStatement.id == Installment.statement_id)
            .join(Category, Category.id == CardPurchase.category_id)
            .where(
                Installment.user_id == user_id,
                CardStatement.reference_month >= first_of_month(f.start),
                CardStatement.reference_month <= f.end,
            )
        )
        if f.category_id:
            stmt = stmt.where(CardPurchase.category_id == f.category_id)
        if f.card_id:
            stmt = stmt.where(CardPurchase.card_id == f.card_id)
        for inst, p, ref, cname in db.execute(stmt).unique().all():
            desc = p.description if p.installments_count == 1 else f"{p.description} ({inst.number}/{p.installments_count})"
            out.append(Line("installment", "expense", inst.amount, ref, desc, p.category_id, cname, p.card_id,
                            extra={"purchase_id": str(p.id)}))

    elif f.basis == "lancamento":
        stmt = (
            select(CardPurchase, Category.name)
            .join(Category, Category.id == CardPurchase.category_id)
            .where(CardPurchase.user_id == user_id, CardPurchase.purchase_date >= f.start, CardPurchase.purchase_date <= f.end)
        )
        if f.category_id:
            stmt = stmt.where(CardPurchase.category_id == f.category_id)
        if f.card_id:
            stmt = stmt.where(CardPurchase.card_id == f.card_id)
        for p, cname in db.execute(stmt).unique().all():
            out.append(Line("purchase", "expense", p.total_amount, p.purchase_date, p.description, p.category_id, cname,
                            p.card_id, extra={"purchase_id": str(p.id), "installments": p.installments_count}))

    else:  # caixa: pagamentos de fatura (sem categoria: a fatura mistura categorias)
        if f.category_id is None:
            stmt = (
                select(StatementPayment, CardStatement)
                .join(CardStatement, CardStatement.id == StatementPayment.statement_id)
                .where(StatementPayment.user_id == user_id, StatementPayment.paid_on >= f.start, StatementPayment.paid_on <= f.end)
            )
            if f.card_id:
                stmt = stmt.where(CardStatement.card_id == f.card_id)
            for pay, st in db.execute(stmt).unique().all():
                out.append(Line("statement_payment", "expense", pay.amount, pay.paid_on,
                                f"Pagamento de fatura · {st.card.nickname}", None, "Fatura de cartão", st.card_id))
    return out


# --------------------------------------------------------------------------- agregações

def summary(db: Session, user_id: uuid.UUID, f: Filters) -> dict:
    ls = lines(db, user_id, f)
    income = q(sum((x.amount for x in ls if x.kind == "income"), ZERO))
    expense = q(sum((x.amount for x in ls if x.kind == "expense"), ZERO))
    expenses = [x for x in ls if x.kind == "expense"]
    largest = max(expenses, key=lambda x: x.amount, default=None)
    cats = by_category_from(expenses)
    return {
        "start": f.start, "end": f.end, "basis": f.basis,
        "income": income, "expense": expense, "balance": income - expense,
        "savings_rate": ((income - expense) / income * 100).quantize(Decimal("0.1")) if income > 0 else None,
        "largest_expense": (
            {"description": largest.description, "amount": q(largest.amount), "day": largest.day,
             "category_name": largest.category_name, "source": largest.source} if largest else None
        ),
        "top_category": cats[0] if cats else None,
        "count": len(ls),
    }


def by_category_from(ls: list[Line]) -> list[dict]:
    totals: dict[tuple, Decimal] = {}
    for x in ls:
        key = (x.category_id, x.category_name)
        totals[key] = totals.get(key, ZERO) + x.amount
    grand = sum(totals.values(), ZERO)
    rows = [
        {"category_id": k[0], "category_name": k[1], "amount": q(v),
         "share": (v / grand * 100).quantize(Decimal("0.1")) if grand else Decimal("0.0")}
        for k, v in totals.items()
    ]
    return sorted(rows, key=lambda r: r["amount"], reverse=True)


def by_category(db: Session, user_id: uuid.UUID, f: Filters, kind: str = "expense") -> list[dict]:
    return by_category_from([x for x in lines(db, user_id, f) if x.kind == kind])


def monthly(db: Session, user_id: uuid.UUID, last_month: date, months: int, basis: Basis,
            category_id: uuid.UUID | None = None, card_id: uuid.UUID | None = None) -> list[dict]:
    """Série mensal de receitas, despesas, resultado e saldo acumulado (somente no intervalo)."""
    first = add_months(first_of_month(last_month), -(months - 1))
    f = Filters(first, month_end(first_of_month(last_month)), basis, category_id, card_id)
    buckets = {add_months(first, i): {"income": ZERO, "expense": ZERO} for i in range(months)}
    for x in lines(db, user_id, f):
        m = first_of_month(x.day)
        if m in buckets:
            buckets[m][x.kind] += x.amount
    out, running = [], ZERO
    for m, v in buckets.items():
        bal = v["income"] - v["expense"]
        running += bal
        out.append({"month": m, "income": q(v["income"]), "expense": q(v["expense"]), "balance": q(bal),
                    "cumulative": q(running)})
    return out


def compare(db: Session, user_id: uuid.UUID, month_a: date, month_b: date, basis: Basis,
            category_id: uuid.UUID | None = None, card_id: uuid.UUID | None = None) -> dict:
    """Compara month_b (atual) com month_a (anterior): diferenças absolutas e percentuais."""
    def period(m: date) -> Filters:
        m = first_of_month(m)
        return Filters(m, month_end(m), basis, category_id, card_id)

    a, b = summary(db, user_id, period(month_a)), summary(db, user_id, period(month_b))
    cats_a = {c["category_name"]: c["amount"] for c in by_category(db, user_id, period(month_a))}
    cats_b = {c["category_name"]: c["amount"] for c in by_category(db, user_id, period(month_b))}
    cat_rows = []
    for name in sorted(set(cats_a) | set(cats_b)):
        va, vb = cats_a.get(name, ZERO), cats_b.get(name, ZERO)
        cat_rows.append({"category_name": name, "previous": va, "current": vb, "diff": vb - va, "pct": pct_change(va, vb)})
    cat_rows.sort(key=lambda r: abs(r["diff"]), reverse=True)

    def diff(key: str) -> dict:
        return {"previous": a[key], "current": b[key], "diff": b[key] - a[key], "pct": pct_change(a[key], b[key])}

    return {"month_a": first_of_month(month_a), "month_b": first_of_month(month_b), "basis": basis,
            "income": diff("income"), "expense": diff("expense"), "balance": diff("balance"), "categories": cat_rows}


def cash_balance(db: Session, user_id: uuid.UUID, until: date) -> Decimal:
    """Saldo calculado: receitas recebidas − despesas pagas − pagamentos de fatura, até a data.
    Não é dinheiro disponível: não desconta compromissos futuros (ver commitments)."""
    inc = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.user_id == user_id, Transaction.kind == "income", Transaction.status == "settled",
        Transaction.occurred_on <= until))
    exp = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.user_id == user_id, Transaction.kind == "expense", Transaction.status == "settled",
        Transaction.occurred_on <= until))
    pay = db.scalar(select(func.coalesce(func.sum(StatementPayment.amount), 0)).where(
        StatementPayment.user_id == user_id, StatementPayment.paid_on <= until))
    return q(Decimal(inc) - Decimal(exp) - Decimal(pay))


def commitments(db: Session, user_id: uuid.UUID, ref: date | None = None, horizon_days: int = 30) -> dict:
    """Compromissos futuros: faturas em aberto, parcelas futuras, contas previstas e lançamentos pendentes."""
    ref = ref or today()
    # Faturas com saldo em aberto (inclui faturas futuras já com parcelas)
    st_rows = db.execute(
        select(CardStatement).where(CardStatement.user_id == user_id).order_by(CardStatement.due_date)
    ).scalars().all()
    from app.services.cards import totals_for  # import local evita ciclo

    totals = totals_for(db, user_id, [s.id for s in st_rows])
    open_statements = []
    for s in st_rows:
        t = totals[s.id]
        if t.remaining > 0:
            open_statements.append({"id": s.id, "card_nickname": s.card.nickname, "reference_month": s.reference_month,
                                    "due_date": s.due_date, "remaining": t.remaining})
    statements_total = q(sum((s["remaining"] for s in open_statements), ZERO))
    # Parcelas futuras = faturas de competência posterior ao mês atual
    future_inst = db.scalar(
        select(func.coalesce(func.sum(Installment.amount), 0))
        .join(CardStatement, CardStatement.id == Installment.statement_id)
        .where(Installment.user_id == user_id, CardStatement.reference_month > first_of_month(ref))
    )
    by_month_rows = db.execute(
        select(CardStatement.reference_month, func.sum(Installment.amount))
        .join(Installment, Installment.statement_id == CardStatement.id)
        .where(Installment.user_id == user_id, CardStatement.reference_month > first_of_month(ref))
        .group_by(CardStatement.reference_month).order_by(CardStatement.reference_month)
    ).all()
    # Contas recorrentes previstas nos próximos dias
    from app.services.bills import ensure_occurrences

    until = ref + timedelta(days=horizon_days)
    ensure_occurrences(db, user_id, ref - timedelta(days=60), until)
    occ = db.scalars(
        select(BillOccurrence).where(BillOccurrence.user_id == user_id, BillOccurrence.status == "pending",
                                     BillOccurrence.due_date <= until).order_by(BillOccurrence.due_date)
    ).all()
    upcoming_bills = [{"id": o.id, "name": o.bill.name, "due_date": o.due_date, "amount": o.amount,
                       "overdue": o.due_date < ref} for o in occ]
    bills_total = q(sum((o.amount or ZERO for o in occ), ZERO))
    pending_tx = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.user_id == user_id, Transaction.kind == "expense", Transaction.status == "pending"))
    return {
        "reference_date": ref,
        "open_statements": open_statements[:12],
        "open_statements_total": statements_total,
        "future_installments_total": q(future_inst),
        "future_installments_by_month": [{"month": m, "amount": q(v)} for m, v in by_month_rows],
        "upcoming_bills": upcoming_bills,
        "upcoming_bills_total": bills_total,
        "pending_expenses_total": q(pending_tx),
        # faturas em aberto já incluem as parcelas futuras; não somar as duas coisas
        "total": q(statements_total + bills_total + Decimal(pending_tx)),
    }


def recent_transactions(db: Session, user_id: uuid.UUID, limit: int = 6) -> list[dict]:
    rows = db.execute(
        select(Transaction, Category.name).join(Category, Category.id == Transaction.category_id)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.occurred_on.desc(), Transaction.created_at.desc()).limit(limit)
    ).all()
    return [{"id": t.id, "kind": t.kind, "description": t.description, "amount": t.amount, "occurred_on": t.occurred_on,
             "category_name": c, "status": t.status} for t, c in rows]

