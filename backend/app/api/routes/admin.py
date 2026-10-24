"""Painel administrativo. Todas as rotas exigem papel ADMIN validado no backend.

O administrador vê somente dados operacionais (nome, e-mail, status, datas).
Não há rotas para ler dados financeiros de outros usuários, e o RLS do banco
também não concede essa visão ao papel ADMIN.
"""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, client_ip, require_admin
from app.config import get_settings
from app.db import get_db
from app.models import AuditLog, Invite, User
from app.schemas import (
    AdminStatsOut,
    AdminUserOut,
    AuditLogOut,
    InviteCreatedOut,
    InviteIn,
    InviteOut,
    MessageOut,
    RegistrationModeIn,
    RegistrationModeOut,
)
from app.security.tokens import hash_token, new_token
from app.services import audit, sessions
from app.services.email import get_email_sender
from app.services.settings_service import get_registration_mode, set_registration_mode

router = APIRouter(prefix="/admin", tags=["administração"])


def _admin_user_out(u: User) -> AdminUserOut:
    return AdminUserOut(
        id=u.id,
        email=u.email,
        display_name=u.display_name,
        role=u.role,
        status=u.status,
        email_verified=u.email_verified_at is not None,
        created_at=u.created_at,
        last_login_at=u.last_login_at,
    )


def _target(db: Session, ctx: AuthContext, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, {"code": "not_found", "message": "Usuário não encontrado."})
    if user.id == ctx.user.id or user.role == "ADMIN":
        raise HTTPException(400, {"code": "not_allowed", "message": "Esta ação não pode ser aplicada a administradores."})
    return user


@router.get("/stats", response_model=AdminStatsOut)
def stats(ctx: AuthContext = Depends(require_admin), db: Session = Depends(get_db)) -> AdminStatsOut:
    rows = db.execute(select(User.status, func.count()).group_by(User.status)).all()
    by_status = {s: c for s, c in rows}
    pending_inv = db.scalar(
        select(func.count()).select_from(Invite).where(
            Invite.used_at.is_(None), Invite.revoked_at.is_(None), Invite.expires_at > sessions.utcnow()
        )
    )
    return AdminStatsOut(total_users=sum(by_status.values()), by_status=by_status, pending_invites=pending_inv or 0)


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    q: str | None = Query(default=None, max_length=100),
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminUserOut]:
    stmt = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    if q:
        like = f"%{q.replace('%', '').replace('_', '')}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.display_name.ilike(like)))
    if status_filter:
        stmt = stmt.where(User.status == status_filter)
    return [_admin_user_out(u) for u in db.scalars(stmt).all()]


def _change_status(
    action: str, allowed_from: tuple[str, ...], new_status: str, user_id: uuid.UUID,
    request: Request, ctx: AuthContext, db: Session,
) -> AdminUserOut:
    user = _target(db, ctx, user_id)
    if user.status not in allowed_from:
        audit.record(db, action, "failure", actor_id=ctx.user.id, actor_email=ctx.user.email,
                     target_user_id=user.id, details={"from": user.status}, ip=client_ip(request))
        db.commit()
        raise HTTPException(409, {"code": "invalid_state", "message": "A conta não está em um estado que permita esta ação."})
    old = user.status
    user.status = new_status
    if new_status in ("suspended", "rejected"):
        sessions.revoke_all(db, user.id)  # encerra sessões imediatamente
    audit.record(db, action, "success", actor_id=ctx.user.id, actor_email=ctx.user.email,
                 target_user_id=user.id, details={"from": old, "to": new_status}, ip=client_ip(request))
    db.commit()
    return _admin_user_out(user)


@router.post("/users/{user_id}/approve", response_model=AdminUserOut)
def approve(user_id: uuid.UUID, request: Request, ctx: AuthContext = Depends(require_admin), db: Session = Depends(get_db)):
    out = _change_status("user_approved", ("pending_approval",), "active", user_id, request, ctx, db)
    get_email_sender().send(out.email, "Sua conta na CarteirIA foi aprovada",
                            "Sua conta foi aprovada. Você já pode entrar na CarteirIA.")
    return out


@router.post("/users/{user_id}/reject", response_model=AdminUserOut)
def reject(user_id: uuid.UUID, request: Request, ctx: AuthContext = Depends(require_admin), db: Session = Depends(get_db)):
    return _change_status("user_rejected", ("pending_approval",), "rejected", user_id, request, ctx, db)


@router.post("/users/{user_id}/suspend", response_model=AdminUserOut)
def suspend(user_id: uuid.UUID, request: Request, ctx: AuthContext = Depends(require_admin), db: Session = Depends(get_db)):
    return _change_status("user_suspended", ("active",), "suspended", user_id, request, ctx, db)


@router.post("/users/{user_id}/reactivate", response_model=AdminUserOut)
def reactivate(user_id: uuid.UUID, request: Request, ctx: AuthContext = Depends(require_admin), db: Session = Depends(get_db)):
    return _change_status("user_reactivated", ("suspended", "rejected"), "active", user_id, request, ctx, db)


@router.get("/registration-mode", response_model=RegistrationModeOut)
def get_mode(ctx: AuthContext = Depends(require_admin), db: Session = Depends(get_db)) -> RegistrationModeOut:
    return RegistrationModeOut(mode=get_registration_mode(db))


@router.put("/registration-mode", response_model=RegistrationModeOut)
def put_mode(body: RegistrationModeIn, request: Request, ctx: AuthContext = Depends(require_admin), db: Session = Depends(get_db)):
    old = get_registration_mode(db)
    set_registration_mode(db, body.mode)
    audit.record(db, "registration_mode_changed", "success", actor_id=ctx.user.id, actor_email=ctx.user.email,
                 details={"from": old, "to": body.mode}, ip=client_ip(request))
    db.commit()
    return RegistrationModeOut(mode=body.mode)


@router.get("/invites", response_model=list[InviteOut])
def list_invites(ctx: AuthContext = Depends(require_admin), db: Session = Depends(get_db)) -> list[InviteOut]:
    rows = db.scalars(select(Invite).order_by(Invite.created_at.desc()).limit(200)).all()
    return [InviteOut.model_validate(r) for r in rows]


@router.post("/invites", response_model=InviteCreatedOut, status_code=201)
def create_invite(body: InviteIn, request: Request, ctx: AuthContext = Depends(require_admin), db: Session = Depends(get_db)):
    s = get_settings()
    email = str(body.email).lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, {"code": "already_registered", "message": "Já existe uma conta com este e-mail."})
    token = new_token()
    inv = Invite(email=email, token_hash=hash_token(token), created_by=ctx.user.id,
                 expires_at=sessions.utcnow() + timedelta(days=s.invite_days))
    db.add(inv)
    db.flush()
    audit.record(db, "invite_created", "success", actor_id=ctx.user.id, actor_email=ctx.user.email,
                 details={"invite_id": str(inv.id), "email": email}, ip=client_ip(request))
    db.commit()
    db.refresh(inv)
    link = f"{s.frontend_url}/cadastro#convite={token}"
    get_email_sender().send(
        email, "Você foi convidado para a CarteirIA",
        f"Você recebeu um convite para criar sua conta na CarteirIA.\n\nAcesse: {link}\n\n"
        f"O convite vale por {s.invite_days} dias, só pode ser usado uma vez e somente com este e-mail.",
    )
    # O link é mostrado uma única vez ao administrador (o banco guarda só o hash).
    return InviteCreatedOut(invite=InviteOut.model_validate(inv), link=link)


@router.delete("/invites/{invite_id}", response_model=MessageOut)
def revoke_invite(invite_id: uuid.UUID, request: Request, ctx: AuthContext = Depends(require_admin), db: Session = Depends(get_db)):
    inv = db.get(Invite, invite_id)
    if inv is None:
        raise HTTPException(404, {"code": "not_found", "message": "Convite não encontrado."})
    if inv.used_at or inv.revoked_at:
        raise HTTPException(409, {"code": "invalid_state", "message": "Este convite já foi usado ou revogado."})
    inv.revoked_at = sessions.utcnow()
    audit.record(db, "invite_revoked", "success", actor_id=ctx.user.id, actor_email=ctx.user.email,
                 details={"invite_id": str(inv.id)}, ip=client_ip(request))
    db.commit()
    return MessageOut(message="Convite revogado.")


@router.get("/audit-logs", response_model=list[AuditLogOut])
def audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    action: str | None = Query(default=None, max_length=64),
    ctx: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AuditLogOut]:
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return [AuditLogOut.model_validate(r) for r in db.scalars(stmt).all()]
