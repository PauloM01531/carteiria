"""Orçamentos mensais por categoria e metas financeiras."""
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Budget, Goal, GoalContribution
from app.services.calendar import add_months, first_of_month, today
from app.services.reports import Filters, lines, month_end, q
from app.services.transactions import validate_category

ZERO = Decimal("0.00")
WARNING_PCT = Decimal("80")


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def spent_by_category(db: Session, user_id: uuid.UUID, month: date) -> dict[uuid.UUID, Decimal]:
    """Despesa por categoria no mês (base competência: lançamentos + parcelas de cartão)."""
    out: dict[uuid.UUID, Decimal] = {}
    for x in lines(db, user_id, Filters(month, month_end(month), "competencia", kind="expense")):
        if x.category_id:
            out[x.category_id] = out.get(x.category_id, ZERO) + x.amount
    return out


def budget_status(spent: Decimal, limit: Decimal) -> tuple[Decimal, str]:
    pct = (spent / limit * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if pct >= 100:
        return pct, "over" if spent > limit else "limit"
    if pct >= WARNING_PCT:
        return pct, "warning"
    return pct, "ok"


def budgets_for_month(db: Session, user_id: uuid.UUID, month: date, history_months: int = 3) -> list[dict]:
    month = first_of_month(month)
    rows = db.scalars(select(Budget).where(Budget.user_id == user_id, Budget.month == month)).all()
    if not rows:
        return []
    spent = spent_by_category(db, user_id, month)
    history = [spent_by_category(db, user_id, add_months(month, -i)) for i in range(1, history_months + 1)]
    out = []
    for b in sorted(rows, key=lambda r: r.category.name):
        s = q(spent.get(b.category_id, ZERO))
        pct, status = budget_status(s, b.limit_amount)
        prev = [q(h.get(b.category_id, ZERO)) for h in history]
        out.append({
            "id": b.id, "category_id": b.category_id, "category_name": b.category.name, "month": b.month,
            "limit_amount": b.limit_amount, "spent": s, "remaining": b.limit_amount - s, "percent": pct, "status": status,
            "previous_months": [{"month": add_months(month, -(i + 1)), "spent": v} for i, v in enumerate(prev)],
            "previous_average": q(sum(prev, ZERO) / len(prev)) if prev else ZERO,
        })
    return out


def create_budget(db: Session, user_id: uuid.UUID, category_id: uuid.UUID, month: date, limit_amount: Decimal) -> Budget:
    validate_category(db, user_id, category_id, "expense")
    month = first_of_month(month)
    exists = db.scalar(select(Budget.id).where(Budget.user_id == user_id, Budget.category_id == category_id, Budget.month == month))
    if exists:
        raise _err(409, "duplicate", "Já existe um orçamento para essa categoria neste mês.")
    b = Budget(user_id=user_id, category_id=category_id, month=month, limit_amount=limit_amount)
    db.add(b)
    db.flush()
    return b


def get_budget(db: Session, user_id: uuid.UUID, budget_id: uuid.UUID) -> Budget:
    b = db.scalar(select(Budget).where(Budget.id == budget_id, Budget.user_id == user_id))
    if b is None:
        raise _err(404, "not_found", "Orçamento não encontrado.")
    return b


def copy_budgets(db: Session, user_id: uuid.UUID, source: date, target: date) -> int:
    """Copia os limites de um mês para outro, sem sobrescrever os já existentes."""
    source, target = first_of_month(source), first_of_month(target)
    existing = set(db.scalars(select(Budget.category_id).where(Budget.user_id == user_id, Budget.month == target)))
    created = 0
    for b in db.scalars(select(Budget).where(Budget.user_id == user_id, Budget.month == source)).all():
        if b.category_id not in existing and b.category.active:
            db.add(Budget(user_id=user_id, category_id=b.category_id, month=target, limit_amount=b.limit_amount))
            created += 1
    db.flush()
    return created


# --------------------------------------------------------------------------- metas

def goal_view(g: Goal, ref: date | None = None) -> dict:
    ref = ref or today()
    saved = q(sum((c.amount for c in g.contributions), ZERO))
    remaining = max(g.target_amount - saved, ZERO)
    pct = min((saved / g.target_amount * 100), Decimal(100)).quantize(Decimal("0.1")) if saved > 0 else Decimal("0.0")
    monthly_needed = None
    months_left = None
    if g.deadline and remaining > 0:
        months_left = max((g.deadline.year - ref.year) * 12 + g.deadline.month - ref.month, 0)
        monthly_needed = q(remaining / months_left) if months_left > 0 else remaining
    status = "achieved" if saved >= g.target_amount else ("late" if g.deadline and g.deadline < ref else "in_progress")
    return {
        "id": g.id, "name": g.name, "target_amount": g.target_amount, "deadline": g.deadline, "notes": g.notes,
        "saved": saved, "remaining": remaining, "percent": pct, "status": status,
        "months_left": months_left, "monthly_needed": monthly_needed,
        "contributions": [{"id": c.id, "amount": c.amount, "contributed_on": c.contributed_on, "notes": c.notes}
                          for c in g.contributions],
    }


def get_goal(db: Session, user_id: uuid.UUID, goal_id: uuid.UUID) -> Goal:
    g = db.scalar(select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id))
    if g is None:
        raise _err(404, "not_found", "Meta não encontrada.")
    return g


def add_contribution(db: Session, user_id: uuid.UUID, goal_id: uuid.UUID, amount: Decimal, day: date,
                     notes: str | None) -> Goal:
    g = get_goal(db, user_id, goal_id)
    saved = sum((c.amount for c in g.contributions), ZERO)
    if saved + amount < 0:
        raise _err(422, "negative_balance", "A retirada é maior que o valor guardado na meta.")
    db.add(GoalContribution(user_id=user_id, goal_id=g.id, amount=amount, contributed_on=day, notes=notes))
    db.flush()
    db.refresh(g)
    return g


def delete_contribution(db: Session, user_id: uuid.UUID, goal_id: uuid.UUID, contribution_id: uuid.UUID) -> None:
    c = db.scalar(select(GoalContribution).where(GoalContribution.id == contribution_id, GoalContribution.goal_id == goal_id,
                                                 GoalContribution.user_id == user_id))
    if c is None:
        raise _err(404, "not_found", "Movimentação não encontrada.")
    db.delete(c)
