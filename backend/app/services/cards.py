"""Regras de cartões de crédito, compras parceladas e faturas.

Conceitos (separados para evitar duplicidade em relatórios):
- data da compra: quando a compra aconteceu;
- competência: mês de referência da fatura onde a parcela é cobrada;
- pagamento da fatura: quando e quanto foi pago.

Uma compra de R$ 1.200,00 em 12x gera 12 parcelas de R$ 100,00, uma em cada fatura.
"""
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Card, CardPurchase, CardStatement, Installment, StatementPayment
from app.services.calendar import add_months, clamp_day, first_of_month, today
from app.services.transactions import validate_category

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def brl(v: Decimal) -> str:
    """Decimal -> 'R$ 1.234,56' (mensagens de erro)."""
    s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "_").replace(".", ",").replace("_", ".")


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


# --------------------------------------------------------------------------- regras puras

def split_installments(total: Decimal, count: int) -> list[Decimal]:
    """Divide em parcelas iguais; a diferença de centavos vai para a ÚLTIMA parcela,
    garantindo que a soma seja exatamente o total."""
    if count < 1:
        raise ValueError("count deve ser >= 1")
    cents = int((total / CENT).to_integral_value())
    base = cents // count
    if base == 0:
        raise _err(422, "amount_too_small", "O valor é pequeno demais para esse número de parcelas.")
    parts = [base] * count
    parts[-1] += cents - base * count
    return [Decimal(p) * CENT for p in parts]


def suggest_reference_month(closing_day: int, purchase_date: date) -> date:
    """Compras ANTES do dia de fechamento entram na fatura que fecha naquele mês;
    no dia do fechamento ou depois, entram na fatura do mês seguinte."""
    closing = clamp_day(purchase_date.year, purchase_date.month, closing_day)
    ref = first_of_month(purchase_date)
    return ref if purchase_date < closing else add_months(ref, 1)


def statement_dates(closing_day: int, due_day: int, reference_month: date) -> tuple[date, date]:
    """Fechamento no mês de referência; vencimento no mesmo mês se o dia de vencimento
    for depois do fechamento, senão no mês seguinte."""
    closing = clamp_day(reference_month.year, reference_month.month, closing_day)
    due_month = reference_month if due_day > closing_day else add_months(reference_month, 1)
    return closing, clamp_day(due_month.year, due_month.month, due_day)


def statement_status(total: Decimal, paid: Decimal, closing: date, due: date, ref_today: date) -> str:
    if total > 0 and paid >= total:
        return "paid"
    if total == 0 and paid == 0:
        return "empty"
    if ref_today > due:
        return "overdue"
    if paid > 0:
        return "partial"
    if ref_today >= closing:
        return "closed"
    return "open"


# --------------------------------------------------------------------------- acesso com dono

def get_card(db: Session, user_id: uuid.UUID, card_id: uuid.UUID) -> Card:
    card = db.scalar(select(Card).where(Card.id == card_id, Card.user_id == user_id))
    if card is None:
        raise _err(404, "not_found", "Cartão não encontrado.")
    return card


def get_purchase(db: Session, user_id: uuid.UUID, purchase_id: uuid.UUID) -> CardPurchase:
    p = db.scalar(select(CardPurchase).where(CardPurchase.id == purchase_id, CardPurchase.user_id == user_id))
    if p is None:
        raise _err(404, "not_found", "Compra não encontrada.")
    return p


def get_statement(db: Session, user_id: uuid.UUID, statement_id: uuid.UUID) -> CardStatement:
    s = db.scalar(select(CardStatement).where(CardStatement.id == statement_id, CardStatement.user_id == user_id))
    if s is None:
        raise _err(404, "not_found", "Fatura não encontrada.")
    return s


def get_or_create_statement(db: Session, user_id: uuid.UUID, card: Card, reference_month: date) -> CardStatement:
    closing, due = statement_dates(card.closing_day, card.due_day, reference_month)
    # ON CONFLICT: nunca cria duas faturas para o mesmo cartão e competência.
    db.execute(
        insert(CardStatement)
        .values(user_id=user_id, card_id=card.id, reference_month=reference_month, closing_date=closing, due_date=due)
        .on_conflict_do_nothing(index_elements=["card_id", "reference_month"])
    )
    st = db.scalar(
        select(CardStatement).where(
            CardStatement.card_id == card.id,
            CardStatement.reference_month == reference_month,
            CardStatement.user_id == user_id,
        )
    )
    assert st is not None
    return st


# --------------------------------------------------------------------------- totais

@dataclass
class StatementTotals:
    total: Decimal
    paid: Decimal
    count: int

    @property
    def remaining(self) -> Decimal:
        return max(self.total - self.paid, ZERO)


def totals_for(db: Session, user_id: uuid.UUID, statement_ids: list[uuid.UUID]) -> dict[uuid.UUID, StatementTotals]:
    if not statement_ids:
        return {}
    inst = dict(
        (sid, (Decimal(t), c))
        for sid, t, c in db.execute(
            select(Installment.statement_id, func.sum(Installment.amount), func.count(Installment.id))
            .where(Installment.user_id == user_id, Installment.statement_id.in_(statement_ids))
            .group_by(Installment.statement_id)
        ).all()
    )
    pays = dict(
        (sid, Decimal(t))
        for sid, t in db.execute(
            select(StatementPayment.statement_id, func.sum(StatementPayment.amount))
            .where(StatementPayment.user_id == user_id, StatementPayment.statement_id.in_(statement_ids))
            .group_by(StatementPayment.statement_id)
        ).all()
    )
    out = {}
    for sid in statement_ids:
        total, count = inst.get(sid, (ZERO, 0))
        out[sid] = StatementTotals(total=total.quantize(CENT), paid=pays.get(sid, ZERO).quantize(CENT), count=count)
    return out


def card_used_amount(db: Session, user_id: uuid.UUID, card_id: uuid.UUID) -> Decimal:
    """Limite comprometido = soma do que falta pagar em todas as faturas do cartão."""
    ids = list(db.scalars(select(CardStatement.id).where(CardStatement.card_id == card_id, CardStatement.user_id == user_id)))
    return sum((t.remaining for t in totals_for(db, user_id, ids).values()), ZERO)


# --------------------------------------------------------------------------- compras

def _ensure_unlocked(db: Session, user_id: uuid.UUID, statement_ids: list[uuid.UUID]) -> None:
    if not statement_ids:
        return
    has_payment = db.scalar(
        select(func.count(StatementPayment.id)).where(
            StatementPayment.user_id == user_id, StatementPayment.statement_id.in_(statement_ids)
        )
    )
    if has_payment:
        raise _err(
            409,
            "statement_has_payment",
            "Esta compra está em uma fatura com pagamento registrado. Exclua o pagamento antes de alterar os valores.",
        )


def _generate_installments(db: Session, user_id: uuid.UUID, purchase: CardPurchase, card: Card) -> None:
    amounts = split_installments(purchase.total_amount, purchase.installments_count)
    for i, amount in enumerate(amounts):
        st = get_or_create_statement(db, user_id, card, add_months(purchase.first_statement_month, i))
        db.add(Installment(user_id=user_id, purchase_id=purchase.id, statement_id=st.id, number=i + 1, amount=amount))


def _cleanup_empty_statements(db: Session, user_id: uuid.UUID, statement_ids: set[uuid.UUID]) -> None:
    for sid in statement_ids:
        has_inst = db.scalar(select(func.count(Installment.id)).where(Installment.statement_id == sid))
        has_pay = db.scalar(select(func.count(StatementPayment.id)).where(StatementPayment.statement_id == sid))
        if not has_inst and not has_pay:
            db.execute(delete(CardStatement).where(CardStatement.id == sid, CardStatement.user_id == user_id))


def create_purchase(db: Session, user_id: uuid.UUID, data: dict) -> CardPurchase:
    """Operação transacional: compra + parcelas + faturas são gravadas juntas ou nada é gravado."""
    card = get_card(db, user_id, data["card_id"])
    if not card.active:
        raise _err(422, "inactive_card", "Este cartão está inativo.")
    validate_category(db, user_id, data["category_id"], "expense")
    if data.get("first_statement_month") is None:
        data["first_statement_month"] = suggest_reference_month(card.closing_day, data["purchase_date"])
    purchase = CardPurchase(user_id=user_id, **data)
    db.add(purchase)
    db.flush()
    _generate_installments(db, user_id, purchase, card)
    db.flush()
    db.refresh(purchase)
    return purchase


FINANCIAL_FIELDS = {"card_id", "total_amount", "installments_count", "first_statement_month"}


def update_purchase(db: Session, user_id: uuid.UUID, purchase_id: uuid.UUID, changes: dict) -> CardPurchase:
    purchase = get_purchase(db, user_id, purchase_id)
    if "category_id" in changes:
        validate_category(db, user_id, changes["category_id"], "expense", allow_inactive_id=purchase.category_id)
    regenerate = any(k in changes and changes[k] != getattr(purchase, k) for k in FINANCIAL_FIELDS)
    if regenerate:
        old_statements = {i.statement_id for i in purchase.installments}
        _ensure_unlocked(db, user_id, list(old_statements))
        card = get_card(db, user_id, changes.get("card_id", purchase.card_id))
        if not card.active and card.id != purchase.card_id:
            raise _err(422, "inactive_card", "Este cartão está inativo.")
        for k, v in changes.items():
            setattr(purchase, k, v)
        purchase.installments.clear()
        db.flush()
        _generate_installments(db, user_id, purchase, card)
        db.flush()
        _cleanup_empty_statements(db, user_id, old_statements)
    else:
        for k, v in changes.items():
            setattr(purchase, k, v)
    db.flush()
    db.refresh(purchase)
    return purchase


def delete_purchase(db: Session, user_id: uuid.UUID, purchase_id: uuid.UUID) -> None:
    purchase = get_purchase(db, user_id, purchase_id)
    old_statements = {i.statement_id for i in purchase.installments}
    _ensure_unlocked(db, user_id, list(old_statements))
    db.delete(purchase)
    db.flush()
    _cleanup_empty_statements(db, user_id, old_statements)


# --------------------------------------------------------------------------- pagamentos

def add_payment(db: Session, user_id: uuid.UUID, statement_id: uuid.UUID, amount: Decimal, paid_on: date,
                notes: str | None) -> StatementPayment:
    st = get_statement(db, user_id, statement_id)
    t = totals_for(db, user_id, [st.id])[st.id]
    if t.total == 0:
        raise _err(422, "empty_statement", "Esta fatura não tem valores a pagar.")
    if amount > t.remaining:
        raise _err(422, "overpayment", f"O valor excede o saldo da fatura ({brl(t.remaining)}).")
    p = StatementPayment(user_id=user_id, statement_id=st.id, amount=amount, paid_on=paid_on, notes=notes)
    db.add(p)
    db.flush()
    return p


def delete_payment(db: Session, user_id: uuid.UUID, statement_id: uuid.UUID, payment_id: uuid.UUID) -> None:
    p = db.scalar(
        select(StatementPayment).where(
            StatementPayment.id == payment_id,
            StatementPayment.statement_id == statement_id,
            StatementPayment.user_id == user_id,
        )
    )
    if p is None:
        raise _err(404, "not_found", "Pagamento não encontrado.")
    db.delete(p)


def ref_today() -> date:
    return today()
