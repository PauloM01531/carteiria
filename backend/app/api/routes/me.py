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
    MfaCodeIn,
    MfaDisableIn,
    MfaSetupIn,
    MfaSetupOut,
    MfaStatusOut,
    PreferencesIn,
    PreferencesOut,
    ProfileUpdateIn,
    UserOut,
)
from app.security import mfa, passwords
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


# ---------------------------------------------------------------- verificação em duas etapas (MFA)

@router.get("/mfa", response_model=MfaStatusOut)
def mfa_status(ctx: AuthContext = Depends(get_auth)) -> MfaStatusOut:
    return MfaStatusOut(enabled=ctx.user.mfa_enabled, required=ctx.user.role == "ADMIN")


@router.post("/mfa/setup", response_model=MfaSetupOut)
def mfa_setup(body: MfaSetupIn, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> MfaSetupOut:
    """Gera um novo segredo (ainda inativo). Só passa a valer após confirmar um código em /mfa/enable."""
    enforce(f"mfa-setup:user:{ctx.user.id}", limit=5, window_seconds=15 * 60)
    if ctx.user.mfa_enabled:
        raise HTTPException(409, {"code": "already_enabled", "message": "A verificação em duas etapas já está ativa."})
    if not passwords.verify_password(ctx.user.password_hash, body.password):
        raise HTTPException(400, {"code": "invalid_password", "message": "Senha incorreta."})
    secret = mfa.new_secret()
    ctx.user.mfa_secret_enc = mfa.encrypt(secret)
    ctx.user.mfa_last_step = None
    db.commit()
    return MfaSetupOut(secret=secret, otpauth_uri=mfa.provisioning_uri(secret, ctx.user.email))


@router.post("/mfa/enable", response_model=MessageOut)
def mfa_enable(body: MfaCodeIn, request: Request, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> MessageOut:
    enforce(f"mfa-enable:user:{ctx.user.id}", limit=10, window_seconds=15 * 60)
    secret = mfa.decrypt(ctx.user.mfa_secret_enc or "")
    if ctx.user.mfa_enabled or not secret:
        raise HTTPException(409, {"code": "invalid_state", "message": "Gere um novo código QR antes de ativar."})
    step = mfa.check_code(secret, body.code, ctx.user.mfa_last_step)
    if step is None:
        raise HTTPException(400, {"code": "invalid_code", "message": "Código inválido. Confira o aplicativo e tente de novo."})
    from app.services.sessions import revoke_all, utcnow

    ctx.user.mfa_enabled_at = utcnow()
    ctx.user.mfa_last_step = step
    ctx.session.mfa_verified = True
    ctx.session.reauth_at = utcnow()
    revoke_all(db, ctx.user.id, except_id=ctx.session.id)  # outras sessões não passaram pelo 2º fator
    audit.record(db, "mfa_enabled", "success", actor_id=ctx.user.id, ip=client_ip(request))
    db.commit()
    return MessageOut(message="Verificação em duas etapas ativada.")


@router.post("/mfa/disable", response_model=MessageOut)
def mfa_disable(body: MfaDisableIn, request: Request, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> MessageOut:
    enforce(f"mfa-disable:user:{ctx.user.id}", limit=5, window_seconds=15 * 60)
    if ctx.user.role == "ADMIN":
        raise HTTPException(400, {"code": "admin_requires_mfa", "message": "A conta administrativa precisa manter a verificação em duas etapas."})
    if not ctx.user.mfa_enabled:
        raise HTTPException(409, {"code": "invalid_state", "message": "A verificação em duas etapas não está ativa."})
    if not passwords.verify_password(ctx.user.password_hash, body.password):
        raise HTTPException(400, {"code": "invalid_password", "message": "Senha incorreta."})
    if mfa.check_code(mfa.decrypt(ctx.user.mfa_secret_enc or "") or "", body.code, ctx.user.mfa_last_step) is None:
        raise HTTPException(400, {"code": "invalid_code", "message": "Código inválido."})
    ctx.user.mfa_enabled_at = None
    ctx.user.mfa_secret_enc = None
    ctx.user.mfa_last_step = None
    audit.record(db, "mfa_disabled", "success", actor_id=ctx.user.id, ip=client_ip(request))
    db.commit()
    return MessageOut(message="Verificação em duas etapas desativada.")
