"""Contas recorrentes (aluguel, energia, assinaturas...).

- Cada conta gera ocorrências por vencimento; o índice único (conta, vencimento) impede duplicatas.
- Ocorrência PENDENTE é previsão: não entra como despesa.
- Ao marcar como paga, é criado UM lançamento de despesa (pago); desfazer o pagamento remove esse lançamento.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import BillOccurrence, RecurringBill, Transaction
from app.models.cards import FREQ_MONTHS
from app.services.calendar import add_months, clamp_day, first_of_month, today
from app.services.transactions import validate_category

MAX_HORIZON_DAYS = 400   # gera previsões no máximo ~13 meses à frente
DUE_SOON_DAYS = 7


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def due_dates(bill: RecurringBill, start: date, end: date) -> list[date]:
    """Vencimentos da conta dentro de [start, end], respeitando início, fim e periodicidade."""
    step = FREQ_MONTHS[bill.frequency]
    out = []
    month = first_of_month(bill.start_date)
    last = min(end, bill.end_date) if bill.end_date else end
    while month <= last:
        d = clamp_day(month.year, month.month, bill.due_day)
        if d >= bill.start_date and start <= d <= last:
            out.append(d)
        month = add_months(month, step)
    return out


def get_bill(db: Session, user_id: uuid.UUID, bill_id: uuid.UUID) -> RecurringBill:
    b = db.scalar(select(RecurringBill).where(RecurringBill.id == bill_id, RecurringBill.user_id == user_id))
    if b is None:
        raise _err(404, "not_found", "Conta não encontrada.")
    return b


def get_occurrence(db: Session, user_id: uuid.UUID, occ_id: uuid.UUID) -> BillOccurrence:
    o = db.scalar(select(BillOccurrence).where(BillOccurrence.id == occ_id, BillOccurrence.user_id == user_id))
    if o is None:
        raise _err(404, "not_found", "Ocorrência não encontrada.")
    return o


def ensure_occurrences(db: Session, user_id: uuid.UUID, start: date, end: date) -> None:
    end = min(end, today() + timedelta(days=MAX_HORIZON_DAYS))
    if end < start:
        return
    bills = db.scalars(select(RecurringBill).where(RecurringBill.user_id == user_id, RecurringBill.active.is_(True))).all()
    for bill in bills:
        for d in due_dates(bill, start, end):
            db.execute(
                insert(BillOccurrence)
                .values(user_id=user_id, bill_id=bill.id, due_date=d, amount=bill.expected_amount)
                .on_conflict_do_nothing(index_elements=["bill_id", "due_date"])
            )
    db.flush()


def occurrence_state(o: BillOccurrence, ref: date) -> str:
    if o.status == "paid":
        return "paid"
    if o.due_date < ref:
        return "overdue"
    if o.due_date <= ref + timedelta(days=DUE_SOON_DAYS):
        return "due_soon"
    return "pending"


def list_occurrences(db: Session, user_id: uuid.UUID, start: date, end: date) -> list[BillOccurrence]:
    ensure_occurrences(db, user_id, start, end)
    return list(
        db.scalars(
            select(BillOccurrence)
            .where(BillOccurrence.user_id == user_id, BillOccurrence.due_date >= start, BillOccurrence.due_date <= end)
            .order_by(BillOccurrence.due_date)
        ).all()
    )


def create_bill(db: Session, user_id: uuid.UUID, data: dict) -> RecurringBill:
    validate_category(db, user_id, data["category_id"], "expense")
    bill = RecurringBill(user_id=user_id, **data)
    db.add(bill)
    db.flush()
    db.refresh(bill)
    return bill


SCHEDULE_FIELDS = {"frequency", "due_day", "start_date", "end_date"}


def update_bill(db: Session, user_id: uuid.UUID, bill_id: uuid.UUID, changes: dict) -> RecurringBill:
    bill = get_bill(db, user_id, bill_id)
    if "category_id" in changes:
        validate_category(db, user_id, changes["category_id"], "expense", allow_inactive_id=bill.category_id)
    for k, v in changes.items():
        setattr(bill, k, v)
    if bill.amount_type == "fixed" and bill.expected_amount is None:
        raise _err(422, "amount_required", "Informe o valor da conta fixa.")
    if bill.end_date and bill.end_date < bill.start_date:
        raise _err(422, "invalid_period", "A data final deve ser posterior à inicial.")
    pending_future = (
        BillOccurrence.bill_id == bill.id,
        BillOccurrence.status == "pending",
        BillOccurrence.due_date >= today(),
    )
    if SCHEDULE_FIELDS & changes.keys() or changes.get("active") is False:
        # Previsões futuras são refeitas com o novo calendário; o histórico pago é mantido.
        db.execute(delete(BillOccurrence).where(*pending_future))
    elif "expected_amount" in changes:
        for o in db.scalars(select(BillOccurrence).where(*pending_future)):
            o.amount = bill.expected_amount
    db.flush()
    db.refresh(bill)
    return bill


def delete_bill(db: Session, user_id: uuid.UUID, bill_id: uuid.UUID) -> None:
    """Remove a conta e suas previsões. Lançamentos de pagamentos já feitos continuam no histórico."""
    bill = get_bill(db, user_id, bill_id)
    db.delete(bill)


def pay(db: Session, user_id: uuid.UUID, occ_id: uuid.UUID, paid_on: date, amount: Decimal | None,
        payment_method: str) -> BillOccurrence:
    occ = get_occurrence(db, user_id, occ_id)
    if occ.status == "paid":
        raise _err(409, "already_paid", "Esta conta já foi marcada como paga.")
    value = amount or occ.amount
    if value is None:
        raise _err(422, "amount_required", "Informe o valor pago.")
    bill = occ.bill
    tx = Transaction(
        user_id=user_id, kind="expense", description=bill.name, amount=value, occurred_on=paid_on,
        category_id=bill.category_id, payment_method=payment_method, status="settled",
        notes=f"Conta recorrente (vencimento {occ.due_date:%d/%m/%Y})",
    )
    db.add(tx)
    db.flush()
    occ.status, occ.paid_on, occ.amount, occ.transaction_id = "paid", paid_on, value, tx.id
    db.flush()
    return occ


def unpay(db: Session, user_id: uuid.UUID, occ_id: uuid.UUID) -> BillOccurrence:
    occ = get_occurrence(db, user_id, occ_id)
    if occ.status != "paid":
        raise _err(409, "not_paid", "Esta conta não está marcada como paga.")
    if occ.transaction_id:
        db.execute(delete(Transaction).where(Transaction.id == occ.transaction_id, Transaction.user_id == user_id))
    occ.status, occ.paid_on, occ.transaction_id = "pending", None, None
    if occ.bill.amount_type == "fixed":
        occ.amount = occ.bill.expected_amount
    db.flush()
    return occ


def set_amount(db: Session, user_id: uuid.UUID, occ_id: uuid.UUID, amount: Decimal) -> BillOccurrence:
    occ = get_occurrence(db, user_id, occ_id)
    if occ.status == "paid":
        raise _err(409, "already_paid", "Desfaça o pagamento antes de alterar o valor.")
    occ.amount = amount
    db.flush()
    return occ
