"""Regras de lançamentos. Funções puras sobre (sessão, usuário) — reutilizáveis pela futura IA.

Toda função recebe o `user_id` da sessão autenticada (nunca do cliente) e filtra
por ele explicitamente; o RLS do banco é a segunda camada.
"""
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.models import Category, Transaction

ZERO = Decimal("0.00")


@dataclass
class TxFilters:
    start: date | None = None
    end: date | None = None
    kind: str | None = None
    category_id: uuid.UUID | None = None
    payment_method: str | None = None
    status: str | None = None
    q: str | None = None


def _not_found() -> HTTPException:
    return HTTPException(404, {"code": "not_found", "message": "Lançamento não encontrado."})


def visible_category(db: Session, user_id: uuid.UUID, category_id: uuid.UUID) -> Category | None:
    """Categoria do sistema ou do próprio usuário; categorias de outras pessoas não existem para ele."""
    return db.scalar(
        select(Category).where(
            Category.id == category_id,
            or_(Category.user_id.is_(None), Category.user_id == user_id),
        )
    )


def validate_category(db: Session, user_id: uuid.UUID, category_id: uuid.UUID, kind: str,
                      allow_inactive_id: uuid.UUID | None = None) -> Category:
    cat = visible_category(db, user_id, category_id)
    if cat is None:
        raise HTTPException(422, {"code": "invalid_category", "message": "Categoria inválida."})
    if cat.kind != kind:
        msg = "Escolha uma categoria de receita." if kind == "income" else "Escolha uma categoria de despesa."
        raise HTTPException(422, {"code": "category_kind_mismatch", "message": msg})
    if not cat.active and cat.id != allow_inactive_id:
        raise HTTPException(422, {"code": "inactive_category", "message": "Esta categoria está desativada."})
    return cat


def _apply_filters(stmt: Select, user_id: uuid.UUID, f: TxFilters) -> Select:
    stmt = stmt.where(Transaction.user_id == user_id)
    if f.start:
        stmt = stmt.where(Transaction.occurred_on >= f.start)
    if f.end:
        stmt = stmt.where(Transaction.occurred_on <= f.end)
    if f.kind:
        stmt = stmt.where(Transaction.kind == f.kind)
    if f.category_id:
        stmt = stmt.where(Transaction.category_id == f.category_id)
    if f.payment_method:
        stmt = stmt.where(Transaction.payment_method == f.payment_method)
    if f.status:
        stmt = stmt.where(Transaction.status == f.status)
    if f.q:
        term = f.q.replace("\\", "").replace("%", "").replace("_", "").strip()
        if term:
            stmt = stmt.where(Transaction.description.ilike(f"%{term}%"))
    return stmt


def list_transactions(db: Session, user_id: uuid.UUID, f: TxFilters, page: int, page_size: int) -> tuple[list[Transaction], int]:
    base = _apply_filters(select(Transaction), user_id, f)
    total = db.scalar(_apply_filters(select(func.count(Transaction.id)), user_id, f)) or 0
    rows = db.scalars(
        base.order_by(Transaction.occurred_on.desc(), Transaction.created_at.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).unique().all()
    return list(rows), total


def totals(db: Session, user_id: uuid.UUID, f: TxFilters) -> dict:
    """Somas do conjunto filtrado, calculadas no banco com NUMERIC (sem float)."""
    stmt = _apply_filters(
        select(
            func.coalesce(func.sum(case((Transaction.kind == "income", Transaction.amount))), 0),
            func.coalesce(func.sum(case((Transaction.kind == "expense", Transaction.amount))), 0),
            func.count(Transaction.id),
        ),
        user_id,
        f,
    )
    income, expense, count = db.execute(stmt).one()
    income, expense = Decimal(income).quantize(ZERO), Decimal(expense).quantize(ZERO)
    return {"income": income, "expense": expense, "balance": income - expense, "count": count}


def get_owned(db: Session, user_id: uuid.UUID, tx_id: uuid.UUID) -> Transaction:
    tx = db.scalar(select(Transaction).where(Transaction.id == tx_id, Transaction.user_id == user_id))
    if tx is None:  # inexistente ou de outra pessoa: mesma resposta
        raise _not_found()
    return tx


def create(db: Session, user_id: uuid.UUID, data: dict) -> Transaction:
    validate_category(db, user_id, data["category_id"], data["kind"])
    tx = Transaction(user_id=user_id, **data)
    db.add(tx)
    db.flush()
    db.refresh(tx)
    return tx


def update(db: Session, user_id: uuid.UUID, tx_id: uuid.UUID, changes: dict) -> Transaction:
    tx = get_owned(db, user_id, tx_id)
    new_kind = changes.get("kind", tx.kind)
    new_cat = changes.get("category_id", tx.category_id)
    if "kind" in changes or "category_id" in changes:
        # Mantém válida a categoria atual mesmo se tiver sido desativada (preserva o histórico).
        validate_category(db, user_id, new_cat, new_kind, allow_inactive_id=tx.category_id)
    for k, v in changes.items():
        setattr(tx, k, v)
    db.flush()
    db.refresh(tx)
    return tx


def delete(db: Session, user_id: uuid.UUID, tx_id: uuid.UUID) -> None:
    from app.models import BillOccurrence

    tx = get_owned(db, user_id, tx_id)
    # Se o lançamento era o pagamento de uma conta recorrente, a conta volta a ficar pendente.
    for occ in db.scalars(select(BillOccurrence).where(BillOccurrence.transaction_id == tx.id,
                                                       BillOccurrence.user_id == user_id)):
        occ.status, occ.paid_on, occ.transaction_id = "pending", None, None
    db.flush()
    db.delete(tx)
