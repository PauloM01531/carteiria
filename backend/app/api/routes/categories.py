"""Categorias: as do sistema (somente leitura) e as personalizadas do usuário."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app.db import get_db
from app.models import Category
from app.schemas_cards import CategoryCreate, CategoryUpdate
from app.schemas_finance import CategoryOut, Kind

router = APIRouter(prefix="/categories", tags=["categorias"])


def _out(c: Category) -> CategoryOut:
    return CategoryOut(id=c.id, name=c.name, kind=c.kind, active=c.active, is_system=c.user_id is None)


def _name_taken(db: Session, user_id: uuid.UUID, kind: str, name: str, exclude: uuid.UUID | None = None) -> bool:
    stmt = select(Category.id).where(
        Category.kind == kind,
        func.lower(Category.name) == name.lower(),
        or_(Category.user_id.is_(None), Category.user_id == user_id),
    )
    if exclude:
        stmt = stmt.where(Category.id != exclude)
    return db.scalar(stmt) is not None


DUPLICATE = HTTPException(409, {"code": "duplicate", "message": "Já existe uma categoria com esse nome."})


@router.get("", response_model=list[CategoryOut])
def list_categories(
    kind: Kind | None = None,
    include_inactive: bool = False,
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> list[CategoryOut]:
    stmt = select(Category).where(or_(Category.user_id.is_(None), Category.user_id == ctx.user.id))
    if kind:
        stmt = stmt.where(Category.kind == kind)
    if not include_inactive:
        stmt = stmt.where(Category.active.is_(True))
    return [_out(c) for c in db.scalars(stmt.order_by(Category.kind, Category.name)).all()]


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryCreate, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> CategoryOut:
    if _name_taken(db, ctx.user.id, body.kind, body.name):
        raise DUPLICATE
    c = Category(user_id=ctx.user.id, name=body.name, kind=body.kind)
    db.add(c)
    db.flush()
    db.refresh(c)
    out = _out(c)
    db.commit()
    return out


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: uuid.UUID, body: CategoryUpdate, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
) -> CategoryOut:
    c = db.scalar(select(Category).where(Category.id == category_id, or_(Category.user_id.is_(None), Category.user_id == ctx.user.id)))
    if c is None:
        raise HTTPException(404, {"code": "not_found", "message": "Categoria não encontrada."})
    if c.user_id is None:
        raise HTTPException(403, {"code": "system_category", "message": "Categorias padrão não podem ser alteradas."})
    changes = body.model_dump(exclude_unset=True)
    if changes.get("name") and _name_taken(db, ctx.user.id, c.kind, changes["name"], exclude=c.id):
        raise DUPLICATE
    if "name" in changes and changes["name"] is None:
        raise HTTPException(422, {"code": "validation_error", "message": "Informe o nome."})
    # Desativar mantém os lançamentos antigos ligados à categoria (histórico preservado).
    for k, v in changes.items():
        if v is not None:
            setattr(c, k, v)
    db.flush()
    out = _out(c)
    db.commit()
    return out
