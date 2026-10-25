"""Cartões, compras parceladas e faturas. O dono sempre vem da sessão."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth, get_auth_synced
from app.db import get_db
from app.models import Card, CardPurchase, CardStatement, CardSubscription, Installment, StatementPayment
from app.schemas import MessageOut
from app.schemas_cards import (
    CardCreate,
    CardOut,
    CardUpdate,
    InstallmentOut,
    PaymentCreate,
    PaymentOut,
    PurchaseCreate,
    PurchaseOut,
    PurchaseUpdate,
    StatementDetailOut,
    StatementItemOut,
    StatementOut,
    StatementSuggestion,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionUpdate,
)
from app.services import cards as svc
from app.services import subscriptions as subs
from app.services.calendar import first_of_month

router = APIRouter(tags=["cartões e faturas"])


# ---------------------------------------------------------------- cartões

def _card_out(db: Session, user_id: uuid.UUID, c: Card) -> CardOut:
    used = svc.card_used_amount(db, user_id, c.id)
    return CardOut(
        id=c.id, nickname=c.nickname, institution=c.institution, closing_day=c.closing_day, due_day=c.due_day,
        credit_limit=c.credit_limit, active=c.active, used_amount=used,
        available_limit=(c.credit_limit - used) if c.credit_limit is not None else None,
    )


@router.get("/cards", response_model=list[CardOut])
def list_cards(ctx: AuthContext = Depends(get_auth_synced), db: Session = Depends(get_db)) -> list[CardOut]:
    rows = db.scalars(select(Card).where(Card.user_id == ctx.user.id).order_by(Card.active.desc(), Card.nickname)).all()
    return [_card_out(db, ctx.user.id, c) for c in rows]


@router.post("/cards", response_model=CardOut, status_code=201)
def create_card(body: CardCreate, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> CardOut:
    card = Card(user_id=ctx.user.id, **body.model_dump())
    db.add(card)
    db.flush()
    db.refresh(card)
    out = _card_out(db, ctx.user.id, card)
    db.commit()
    return out


@router.get("/cards/{card_id}", response_model=CardOut)
def get_card(card_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_synced), db: Session = Depends(get_db)) -> CardOut:
    return _card_out(db, ctx.user.id, svc.get_card(db, ctx.user.id, card_id))


@router.patch("/cards/{card_id}", response_model=CardOut)
def update_card(card_id: uuid.UUID, body: CardUpdate, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> CardOut:
    card = svc.get_card(db, ctx.user.id, card_id)
    changes = body.model_dump(exclude_unset=True)
    for required in ("nickname", "closing_day", "due_day", "active"):
        if required in changes and changes[required] is None:
            raise HTTPException(422, {"code": "validation_error", "message": "Campo obrigatório não pode ficar vazio."})
    # Mudar os dias vale para novas faturas; faturas existentes mantêm suas datas.
    for k, v in changes.items():
        setattr(card, k, v)
    db.flush()
    out = _card_out(db, ctx.user.id, card)
    db.commit()
    return out


@router.delete("/cards/{card_id}", response_model=MessageOut)
def delete_card(card_id: uuid.UUID, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> MessageOut:
    card = svc.get_card(db, ctx.user.id, card_id)
    if db.scalar(select(func.count(CardPurchase.id)).where(CardPurchase.card_id == card.id)):
        raise HTTPException(409, {"code": "card_in_use", "message": "Este cartão tem compras registradas. Desative-o em vez de excluir."})
    db.delete(card)
    db.commit()
    return MessageOut(message="Cartão excluído.")


@router.get("/cards/{card_id}/suggest-statement", response_model=StatementSuggestion)
def suggest(card_id: uuid.UUID, purchase_date: date, ctx: AuthContext = Depends(get_auth_synced), db: Session = Depends(get_db)):
    card = svc.get_card(db, ctx.user.id, card_id)
    ref = svc.suggest_reference_month(card.closing_day, purchase_date)
    closing, due = svc.statement_dates(card.closing_day, card.due_day, ref)
    return StatementSuggestion(reference_month=ref, closing_date=closing, due_date=due)


# ---------------------------------------------------------------- compras

def _purchase_out(db: Session, p: CardPurchase) -> PurchaseOut:
    refs = dict(db.execute(select(CardStatement.id, CardStatement.reference_month).where(
        CardStatement.id.in_([i.statement_id for i in p.installments]))).all())
    return PurchaseOut(
        id=p.id, card_id=p.card_id, card_nickname=p.card.nickname, description=p.description,
        total_amount=p.total_amount, purchase_date=p.purchase_date, category_id=p.category_id,
        category_name=p.category.name, installments_count=p.installments_count,
        first_statement_month=p.first_statement_month, notes=p.notes, subscription_id=p.subscription_id,
        installments=[InstallmentOut(id=i.id, number=i.number, amount=i.amount, statement_id=i.statement_id,
                                     reference_month=refs[i.statement_id]) for i in p.installments],
    )


@router.get("/card-purchases", response_model=list[PurchaseOut])
def list_purchases(
    card_id: uuid.UUID | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    ctx: AuthContext = Depends(get_auth_synced),
    db: Session = Depends(get_db),
) -> list[PurchaseOut]:
    stmt = select(CardPurchase).where(CardPurchase.user_id == ctx.user.id)
    if card_id:
        stmt = stmt.where(CardPurchase.card_id == card_id)
    if start:
        stmt = stmt.where(CardPurchase.purchase_date >= start)
    if end:
        stmt = stmt.where(CardPurchase.purchase_date <= end)
    rows = db.scalars(stmt.order_by(CardPurchase.purchase_date.desc()).limit(limit)).unique().all()
    return [_purchase_out(db, p) for p in rows]


@router.post("/card-purchases", response_model=PurchaseOut, status_code=201)
def create_purchase(body: PurchaseCreate, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> PurchaseOut:
    p = svc.create_purchase(db, ctx.user.id, body.model_dump())
    out = _purchase_out(db, p)
    db.commit()
    return out


@router.get("/card-purchases/{purchase_id}", response_model=PurchaseOut)
def get_purchase(purchase_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_synced), db: Session = Depends(get_db)) -> PurchaseOut:
    return _purchase_out(db, svc.get_purchase(db, ctx.user.id, purchase_id))


@router.patch("/card-purchases/{purchase_id}", response_model=PurchaseOut)
def update_purchase(purchase_id: uuid.UUID, body: PurchaseUpdate, ctx: AuthContext = Depends(get_auth),
                    db: Session = Depends(get_db)) -> PurchaseOut:
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        if v is None and k != "notes":
            raise HTTPException(422, {"code": "validation_error", "message": "Campo obrigatório não pode ficar vazio."})
    p = svc.update_purchase(db, ctx.user.id, purchase_id, changes)
    out = _purchase_out(db, p)
    db.commit()
    return out


@router.delete("/card-purchases/{purchase_id}", response_model=MessageOut)
def delete_purchase(purchase_id: uuid.UUID, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> MessageOut:
    svc.delete_purchase(db, ctx.user.id, purchase_id)
    db.commit()
    return MessageOut(message="Compra excluída.")


# ---------------------------------------------------------------- faturas

def _statement_outs(db: Session, user_id: uuid.UUID, rows: list[CardStatement]) -> list[StatementOut]:
    totals = svc.totals_for(db, user_id, [s.id for s in rows])
    today = svc.ref_today()
    out = []
    for s in rows:
        t = totals[s.id]
        out.append(StatementOut(
            id=s.id, card_id=s.card_id, card_nickname=s.card.nickname, reference_month=s.reference_month,
            closing_date=s.closing_date, due_date=s.due_date, total=t.total, paid=t.paid, remaining=t.remaining,
            status=svc.statement_status(t.total, t.paid, s.closing_date, s.due_date, today), items_count=t.count,
        ))
    return out


@router.get("/statements", response_model=list[StatementOut])
def list_statements(
    card_id: uuid.UUID | None = None,
    start_month: date | None = None,
    end_month: date | None = None,
    ctx: AuthContext = Depends(get_auth_synced),
    db: Session = Depends(get_db),
) -> list[StatementOut]:
    stmt = select(CardStatement).where(CardStatement.user_id == ctx.user.id)
    if card_id:
        stmt = stmt.where(CardStatement.card_id == card_id)
    if start_month:
        stmt = stmt.where(CardStatement.reference_month >= first_of_month(start_month))
    if end_month:
        stmt = stmt.where(CardStatement.reference_month <= first_of_month(end_month))
    rows = list(db.scalars(stmt.order_by(CardStatement.reference_month, CardStatement.card_id)).all())
    return _statement_outs(db, ctx.user.id, rows)


@router.get("/statements/{statement_id}", response_model=StatementDetailOut)
def get_statement(statement_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_synced), db: Session = Depends(get_db)):
    st = svc.get_statement(db, ctx.user.id, statement_id)
    base = _statement_outs(db, ctx.user.id, [st])[0]
    inst = db.execute(
        select(Installment, CardPurchase)
        .join(CardPurchase, CardPurchase.id == Installment.purchase_id)
        .where(Installment.statement_id == st.id, Installment.user_id == ctx.user.id)
        .order_by(CardPurchase.purchase_date, CardPurchase.description)
    ).unique().all()
    pays = db.scalars(select(StatementPayment).where(
        StatementPayment.statement_id == st.id, StatementPayment.user_id == ctx.user.id).order_by(StatementPayment.paid_on)).all()
    return StatementDetailOut(
        **base.model_dump(),
        items=[StatementItemOut(installment_id=i.id, purchase_id=p.id, description=p.description, purchase_date=p.purchase_date,
                                category_name=p.category.name, number=i.number, installments_count=p.installments_count,
                                amount=i.amount, is_subscription=p.subscription_id is not None) for i, p in inst],
        payments=[PaymentOut(id=p.id, amount=p.amount, paid_on=p.paid_on, notes=p.notes) for p in pays],
    )


@router.post("/statements/{statement_id}/payments", response_model=PaymentOut, status_code=201)
def pay_statement(statement_id: uuid.UUID, body: PaymentCreate, ctx: AuthContext = Depends(get_auth),
                  db: Session = Depends(get_db)) -> PaymentOut:
    p = svc.add_payment(db, ctx.user.id, statement_id, body.amount, body.paid_on, body.notes)
    out = PaymentOut(id=p.id, amount=p.amount, paid_on=p.paid_on, notes=p.notes)
    db.commit()
    return out


@router.delete("/statements/{statement_id}/payments/{payment_id}", response_model=MessageOut)
def delete_payment(statement_id: uuid.UUID, payment_id: uuid.UUID, ctx: AuthContext = Depends(get_auth),
                   db: Session = Depends(get_db)) -> MessageOut:
    svc.delete_payment(db, ctx.user.id, statement_id, payment_id)
    db.commit()
    return MessageOut(message="Pagamento removido.")


# ---------------------------------------------------------------- assinaturas no cartão

def _sub_out(s: CardSubscription) -> SubscriptionOut:
    return SubscriptionOut(
        id=s.id, card_id=s.card_id, card_nickname=s.card.nickname, description=s.description, amount=s.amount,
        category_id=s.category_id, category_name=s.category.name, charge_day=s.charge_day, start_date=s.start_date,
        end_date=s.end_date, active=s.active, notes=s.notes, next_charge=subs.next_charge(s),
    )


@router.get("/card-subscriptions", response_model=list[SubscriptionOut], summary="Assinaturas cobradas no cartão")
def list_subscriptions(card_id: uuid.UUID | None = None, ctx: AuthContext = Depends(get_auth_synced),
                       db: Session = Depends(get_db)) -> list[SubscriptionOut]:
    stmt = select(CardSubscription).where(CardSubscription.user_id == ctx.user.id)
    if card_id:
        stmt = stmt.where(CardSubscription.card_id == card_id)
    rows = db.scalars(stmt.order_by(CardSubscription.active.desc(), CardSubscription.description)).unique().all()
    return [_sub_out(s) for s in rows]


@router.post("/card-subscriptions", response_model=SubscriptionOut, status_code=201)
def create_subscription(body: SubscriptionCreate, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> SubscriptionOut:
    s = subs.create(db, ctx.user.id, body.model_dump())
    out = _sub_out(s)
    db.commit()
    return out


@router.patch("/card-subscriptions/{sub_id}", response_model=SubscriptionOut)
def update_subscription(sub_id: uuid.UUID, body: SubscriptionUpdate, ctx: AuthContext = Depends(get_auth),
                        db: Session = Depends(get_db)) -> SubscriptionOut:
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        if v is None and k not in ("end_date", "notes"):
            raise HTTPException(422, {"code": "validation_error", "message": "Campo obrigatório não pode ficar vazio."})
    s = subs.update(db, ctx.user.id, sub_id, changes)
    out = _sub_out(s)
    db.commit()
    return out


@router.delete("/card-subscriptions/{sub_id}", response_model=MessageOut)
def delete_subscription(sub_id: uuid.UUID, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> MessageOut:
    subs.delete(db, ctx.user.id, sub_id)
    db.commit()
    return MessageOut(message="Assinatura cancelada. As cobranças já feitas continuam nas faturas.")
