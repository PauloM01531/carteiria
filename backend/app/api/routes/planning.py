"""Orçamentos mensais, metas e exportação de dados."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, client_ip, get_auth
from app.db import get_db
from app.models import Goal
from app.schemas import MessageOut
from app.schemas_reports import (
    BudgetCopy,
    BudgetCreate,
    BudgetOut,
    BudgetUpdate,
    ContributionIn,
    GoalCreate,
    GoalOut,
    GoalUpdate,
)
from app.security.rate_limit import enforce
from app.services import audit, export, planning
from app.services.calendar import today

router = APIRouter(tags=["orçamentos, metas e exportação"])


# ---------------------------------------------------------------- orçamentos

@router.get("/budgets", response_model=list[BudgetOut])
def list_budgets(month: date | None = None, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    return planning.budgets_for_month(db, ctx.user.id, month or today())


@router.post("/budgets", response_model=BudgetOut, status_code=201)
def create_budget(body: BudgetCreate, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    b = planning.create_budget(db, ctx.user.id, body.category_id, body.month, body.limit_amount)
    out = next(x for x in planning.budgets_for_month(db, ctx.user.id, b.month) if x["id"] == b.id)
    db.commit()
    return out


@router.patch("/budgets/{budget_id}", response_model=BudgetOut)
def update_budget(budget_id: uuid.UUID, body: BudgetUpdate, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    b = planning.get_budget(db, ctx.user.id, budget_id)
    b.limit_amount = body.limit_amount
    db.flush()
    out = next(x for x in planning.budgets_for_month(db, ctx.user.id, b.month) if x["id"] == b.id)
    db.commit()
    return out


@router.delete("/budgets/{budget_id}", response_model=MessageOut)
def delete_budget(budget_id: uuid.UUID, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    db.delete(planning.get_budget(db, ctx.user.id, budget_id))
    db.commit()
    return MessageOut(message="Orçamento excluído.")


@router.post("/budgets/copy", response_model=MessageOut)
def copy_budgets(body: BudgetCopy, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    n = planning.copy_budgets(db, ctx.user.id, body.source_month, body.target_month)
    db.commit()
    return MessageOut(message=f"{n} orçamento(s) copiado(s).")


# ---------------------------------------------------------------- metas

@router.get("/goals", response_model=list[GoalOut])
def list_goals(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    rows = db.scalars(select(Goal).where(Goal.user_id == ctx.user.id).order_by(Goal.created_at)).unique().all()
    return [planning.goal_view(g) for g in rows]


@router.post("/goals", response_model=GoalOut, status_code=201)
def create_goal(body: GoalCreate, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    g = Goal(user_id=ctx.user.id, **body.model_dump())
    db.add(g)
    db.flush()
    db.refresh(g)
    out = planning.goal_view(g)
    db.commit()
    return out


@router.patch("/goals/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: uuid.UUID, body: GoalUpdate, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    g = planning.get_goal(db, ctx.user.id, goal_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is None and k in ("name", "target_amount"):
            raise HTTPException(422, {"code": "validation_error", "message": "Campo obrigatório não pode ficar vazio."})
        setattr(g, k, v)
    db.flush()
    out = planning.goal_view(g)
    db.commit()
    return out


@router.delete("/goals/{goal_id}", response_model=MessageOut)
def delete_goal(goal_id: uuid.UUID, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    db.delete(planning.get_goal(db, ctx.user.id, goal_id))
    db.commit()
    return MessageOut(message="Meta excluída.")


@router.post("/goals/{goal_id}/contributions", response_model=GoalOut, status_code=201)
def add_contribution(goal_id: uuid.UUID, body: ContributionIn, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    g = planning.add_contribution(db, ctx.user.id, goal_id, body.amount, body.contributed_on, body.notes)
    out = planning.goal_view(g)
    db.commit()
    return out


@router.delete("/goals/{goal_id}/contributions/{contribution_id}", response_model=GoalOut)
def delete_contribution(goal_id: uuid.UUID, contribution_id: uuid.UUID, ctx: AuthContext = Depends(get_auth),
                        db: Session = Depends(get_db)):
    planning.delete_contribution(db, ctx.user.id, goal_id, contribution_id)
    db.flush()
    g = planning.get_goal(db, ctx.user.id, goal_id)
    db.refresh(g)
    out = planning.goal_view(g)
    db.commit()
    return out


# ---------------------------------------------------------------- exportação

def _download(content: bytes, filename: str, media: str) -> Response:
    return Response(content, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Content-Type-Options": "nosniff",
    })


@router.get("/export/all.zip", summary="Todos os meus dados (ZIP com CSVs e perfil)")
def export_all(request: Request, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    enforce(f"export:user:{ctx.user.id}", limit=10, window_seconds=3600)
    content = export.export_all(db, ctx.user)
    audit.record(db, "data_exported", "success", actor_id=ctx.user.id, details={"dataset": "all"}, ip=client_ip(request))
    db.commit()
    return _download(content, f"carteiria-dados-{today():%Y-%m-%d}.zip", "application/zip")


@router.get("/export/{dataset}.csv", summary="Um conjunto de dados em CSV")
def export_csv(dataset: str, start: date | None = None, end: date | None = None,
               ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    if dataset not in export.DATASETS:
        raise HTTPException(404, {"code": "not_found", "message": "Conjunto de dados inexistente."})
    enforce(f"export:user:{ctx.user.id}", limit=60, window_seconds=3600)
    filename, content = export.export_dataset(db, ctx.user.id, dataset, start, end)
    return _download(content, filename, "text/csv; charset=utf-8")

