"""Assinaturas no cartão: cobranças recorrentes mensais.

Cada assinatura gera, para cada mês, UMA compra à vista no cartão na data de cobrança.
A compra entra sozinha na fatura certa (pela regra de fechamento do cartão).

- As cobranças são criadas até ~1 mês à frente, para a próxima fatura já mostrar o valor.
- O índice único (assinatura, data) impede cobrança duplicada no mesmo mês.
- Alterar, pausar ou cancelar a assinatura refaz só as cobranças futuras; o histórico fica.
- Cobranças em faturas com pagamento registrado nunca são removidas automaticamente.
"""
import uuid
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Card, CardPurchase, CardSubscription
from app.services import cards
from app.services.calendar import add_months, clamp_day, first_of_month, today
from app.services.transactions import validate_category

HORIZON_DAYS = 31
NOTE = "Assinatura recorrente"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def charge_dates(sub: CardSubscription, until: date) -> list[date]:
    """Datas de cobrança (uma por mês) entre o início e min(until, fim)."""
    last = min(until, sub.end_date) if sub.end_date else until
    out: list[date] = []
    month = first_of_month(sub.start_date)
    while month <= last:
        d = clamp_day(month.year, month.month, sub.charge_day)
        if sub.start_date <= d <= last:
            out.append(d)
        month = add_months(month, 1)
    return out


def next_charge(sub: CardSubscription, ref: date | None = None) -> date | None:
    if not sub.active:
        return None
    ref = ref or today()
    future = [d for d in charge_dates(sub, ref + timedelta(days=62)) if d > ref]
    return future[0] if future else None


def get_subscription(db: Session, user_id: uuid.UUID, sub_id: uuid.UUID) -> CardSubscription:
    s = db.scalar(select(CardSubscription).where(CardSubscription.id == sub_id, CardSubscription.user_id == user_id))
    if s is None:
        raise _err(404, "not_found", "Assinatura não encontrada.")
    return s


def _generate(db: Session, user_id: uuid.UUID, sub: CardSubscription, card: Card, day: date) -> None:
    purchase = CardPurchase(
        user_id=user_id, card_id=card.id, description=sub.description, total_amount=sub.amount, purchase_date=day,
        category_id=sub.category_id, installments_count=1,
        first_statement_month=cards.suggest_reference_month(card.closing_day, day),
        notes=NOTE, subscription_id=sub.id,
    )
    db.add(purchase)
    db.flush()
    cards._generate_installments(db, user_id, purchase, card)
    db.flush()


def sync(db: Session, user_id: uuid.UUID, ref: date | None = None) -> int:
    """Cria as cobranças que faltam (até ~1 mês à frente). Seguro para chamar várias vezes."""
    until = (ref or today()) + timedelta(days=HORIZON_DAYS)
    created = 0
    subs = db.scalars(
        select(CardSubscription).where(CardSubscription.user_id == user_id, CardSubscription.active.is_(True))
    ).unique().all()
    for sub in subs:
        if not sub.card.active:
            continue
        existing = set(db.scalars(select(CardPurchase.purchase_date).where(
            CardPurchase.subscription_id == sub.id, CardPurchase.user_id == user_id)))
        for day in charge_dates(sub, until):
            if day in existing:
                continue
            try:
                with db.begin_nested():  # outra requisição simultânea pode ter criado a mesma cobrança
                    _generate(db, user_id, sub, sub.card, day)
                created += 1
            except IntegrityError:
                pass
    return created


def remove_future(db: Session, user_id: uuid.UUID, sub: CardSubscription, after: date | None = None) -> None:
    """Remove cobranças futuras ainda não pagas (para refazer com os novos dados ou parar)."""
    after = after or today()
    future = db.scalars(select(CardPurchase.id).where(
        CardPurchase.subscription_id == sub.id, CardPurchase.user_id == user_id, CardPurchase.purchase_date > after)).all()
    for pid in future:
        try:
            with db.begin_nested():
                cards.delete_purchase(db, user_id, pid, from_subscription=True)
        except HTTPException:
            pass  # fatura já tem pagamento: mantém a cobrança


def create(db: Session, user_id: uuid.UUID, data: dict) -> CardSubscription:
    card = cards.get_card(db, user_id, data["card_id"])
    if not card.active:
        raise _err(422, "inactive_card", "Este cartão está inativo.")
    validate_category(db, user_id, data["category_id"], "expense")
    sub = CardSubscription(user_id=user_id, **data)
    db.add(sub)
    db.flush()
    db.refresh(sub)
    sync(db, user_id)
    return sub


def update(db: Session, user_id: uuid.UUID, sub_id: uuid.UUID, changes: dict) -> CardSubscription:
    sub = get_subscription(db, user_id, sub_id)
    if "card_id" in changes and changes["card_id"] != sub.card_id:
        card = cards.get_card(db, user_id, changes["card_id"])
        if not card.active:
            raise _err(422, "inactive_card", "Este cartão está inativo.")
    if "category_id" in changes:
        validate_category(db, user_id, changes["category_id"], "expense", allow_inactive_id=sub.category_id)
    for k, v in changes.items():
        setattr(sub, k, v)
    if sub.end_date and sub.end_date < sub.start_date:
        raise _err(422, "invalid_period", "A data final deve ser posterior à inicial.")
    db.flush()
    db.expire(sub)  # recarrega cartão/categoria se mudaram
    remove_future(db, user_id, sub)
    sync(db, user_id)
    db.refresh(sub)
    return sub


def delete(db: Session, user_id: uuid.UUID, sub_id: uuid.UUID) -> None:
    """Cancela: remove cobranças futuras não pagas; as passadas ficam no histórico das faturas."""
    sub = get_subscription(db, user_id, sub_id)
    remove_future(db, user_id, sub)
    db.delete(sub)
    db.flush()
