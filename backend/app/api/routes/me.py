"""Perfil, preferências, sessões ativas e exclusão da própria conta."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, client_ip, get_auth
from app.api.routes.auth import _clear_session_cookie
from app.db import get_db
from app.models import User, UserPreferences, UserSession
from app.schemas import (
    DeleteAccountIn,
    DeviceSessionOut,
    MessageOut,
    PreferencesIn,
    PreferencesOut,
    ProfileUpdateIn,
    UserOut,
)
from app.security import passwords
from app.security.rate_limit import enforce
from app.services import audit

router = APIRouter(prefix="/me", tags=["perfil"])

NOT_FOUND = HTTPException(404, {"code": "not_found", "message": "Registro não encontrado."})


@router.get("", response_model=UserOut)
def get_profile(ctx: AuthContext = Depends(get_auth)) -> UserOut:
    return UserOut.model_validate(ctx.user)


@router.patch("", response_model=UserOut)
def update_profile(
    body: ProfileUpdateIn, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
) -> UserOut:
    ctx.user.display_name = body.display_name
    db.commit()
    return UserOut.model_validate(ctx.user)


@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> PreferencesOut:
    # O RLS já restringe às linhas do usuário; o filtro explícito é uma segunda camada.
    prefs = db.scalar(select(UserPreferences).where(UserPreferences.user_id == ctx.user.id))
    return PreferencesOut(theme=prefs.theme if prefs else "system")


@router.put("/preferences", response_model=PreferencesOut)
def put_preferences(
    body: PreferencesIn, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
) -> PreferencesOut:
    prefs = db.get(UserPreferences, ctx.user.id)
    if prefs is None:
        prefs = UserPreferences(user_id=ctx.user.id, theme=body.theme)
        db.add(prefs)
    else:
        prefs.theme = body.theme
    db.commit()
    return PreferencesOut(theme=prefs.theme)


@router.get("/sessions", response_model=list[DeviceSessionOut])
def list_sessions(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> list[DeviceSessionOut]:
    rows = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == ctx.user.id, UserSession.revoked_at.is_(None))
        .order_by(UserSession.last_seen_at.desc())
    ).all()
    out = []
    for r in rows:
        item = DeviceSessionOut.model_validate(r)
        item.current = r.id == ctx.session.id
        out.append(item)
    return out


@router.delete("/sessions/{session_id}", response_model=MessageOut)
def revoke_session(
    session_id: uuid.UUID, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
) -> MessageOut:
    sess = db.scalar(
        select(UserSession).where(UserSession.id == session_id, UserSession.user_id == ctx.user.id)
    )
    if sess is None:  # inexistente ou de outra pessoa: mesma resposta
        raise NOT_FOUND
    from app.services.sessions import utcnow

    sess.revoked_at = utcnow()
    db.commit()
    return MessageOut(message="Sessão encerrada.")


@router.delete("", response_model=MessageOut)
def delete_account(
    body: DeleteAccountIn,
    request: Request,
    response: Response,
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> MessageOut:
    """Exclui a conta e, em cascata, todos os dados pessoais e financeiros do usuário.
    Fica apenas um registro de auditoria com o id (sem e-mail), conforme docs/PRIVACIDADE.md."""
    enforce(f"delete-account:user:{ctx.user.id}", limit=5, window_seconds=15 * 60)
    if not passwords.verify_password(ctx.user.password_hash, body.password):
        raise HTTPException(400, {"code": "invalid_password", "message": "Senha incorreta."})
    if ctx.user.role == "ADMIN":
        raise HTTPException(
            400,
            {"code": "admin_cannot_delete", "message": "A conta do administrador principal não pode ser excluída por aqui."},
        )
    user_id = ctx.user.id
    audit.record(db, "account_deleted", "success", actor_id=user_id, target_user_id=user_id, ip=client_ip(request))
    db.execute(delete(User).where(User.id == user_id))
    db.commit()
    _clear_session_cookie(response)
    return MessageOut(message="Sua conta e seus dados foram excluídos.")
