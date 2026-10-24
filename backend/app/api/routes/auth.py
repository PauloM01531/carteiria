"""Cadastro, verificação de e-mail, login, logout e recuperação de senha."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, client_ip, get_auth, session_cookie_name
from app.config import get_settings
from app.db import get_db
from app.models import AuthToken, Invite, User
from app.schemas import (
    ChangePasswordIn,
    EmailIn,
    LoginIn,
    MessageOut,
    MfaChallengeOut,
    MfaLoginIn,
    ReauthIn,
    RegisterIn,
    ResetPasswordIn,
    SessionOut,
    TokenIn,
    UserOut,
)
from app.security import mfa, passwords
from app.security.rate_limit import enforce
from app.security.tokens import csrf_for_session, hash_token
from app.services import audit, auth_tokens, sessions
from app.services.email import get_email_sender
from app.services.settings_service import get_registration_mode

router = APIRouter(prefix="/auth", tags=["autenticação"])

GENERIC_REGISTER = "Se os dados estiverem corretos, enviaremos um e-mail para confirmar o endereço."
GENERIC_FORGOT = "Se houver uma conta com este e-mail, enviaremos as instruções de redefinição."
HOUR = 3600


def _err(code: int, key: str, message: str) -> HTTPException:
    return HTTPException(code, {"code": key, "message": message})


def _check_password(password: str, email: str) -> None:
    problems = passwords.password_problems(password, email)
    if problems:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "weak_password", " ".join(problems))


def _set_session_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        session_cookie_name(),
        token,
        max_age=s.session_absolute_hours * HOUR,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(
        session_cookie_name(), path="/", secure=s.cookie_secure, httponly=True, samesite="lax"
    )


def _send_verification(db: Session, user: User) -> None:
    s = get_settings()
    token = auth_tokens.issue(db, user.id, "verify_email", timedelta(hours=s.email_token_hours))
    # O token vai no fragmento (#): não é enviado a servidores nem aparece em logs de acesso.
    link = f"{s.frontend_url}/verificar-email#token={token}"
    get_email_sender().send(
        user.email,
        "Confirme seu e-mail na CarteirIA",
        f"Olá, {user.display_name}!\n\nPara confirmar seu e-mail, acesse:\n{link}\n\n"
        f"O link vale por {s.email_token_hours} horas. Se você não criou esta conta, ignore esta mensagem.",
    )


def _find_valid_invite(db: Session, token: str) -> Invite | None:
    inv = db.scalar(select(Invite).where(Invite.token_hash == hash_token(token)).with_for_update())
    if inv is None or inv.used_at or inv.revoked_at or inv.expires_at <= sessions.utcnow():
        return None
    return inv


@router.post("/register", response_model=MessageOut, status_code=status.HTTP_202_ACCEPTED)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)) -> MessageOut:
    ip = client_ip(request)
    enforce(f"register:ip:{ip}", limit=5, window_seconds=HOUR)
    email = str(body.email).lower()
    _check_password(body.password, email)

    mode = get_registration_mode(db)
    if mode == "closed":
        raise _err(403, "registration_closed", "Novos cadastros estão fechados no momento.")

    invite = None
    if body.invite_token:
        invite = _find_valid_invite(db, body.invite_token)
        # O convite só vale para o e-mail ao qual foi destinado.
        if invite is None or invite.email.lower() != email:
            raise _err(400, "invalid_invite", "Convite inválido, expirado ou destinado a outro e-mail.")
    elif mode == "invite":
        raise _err(403, "invite_required", "No momento, o cadastro é feito somente por convite.")

    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        # Não revela que a conta existe; avisa o dono do e-mail.
        get_email_sender().send(
            existing.email,
            "Tentativa de cadastro na CarteirIA",
            "Alguém tentou criar uma conta com o seu e-mail. Se foi você, use 'Esqueci minha senha'.",
        )
        return MessageOut(message=GENERIC_REGISTER)

    user = User(
        email=email,
        display_name=body.display_name,
        password_hash=passwords.hash_password(body.password),
        status="active" if invite else "pending_approval",
    )
    db.add(user)
    db.flush()
    if invite:
        invite.used_at = sessions.utcnow()
        invite.used_by = user.id
    audit.record(
        db,
        "user_registered",
        "success",
        actor_id=user.id,
        target_user_id=user.id,
        details={"via": "invite" if invite else mode},
        ip=ip,
    )
    _send_verification(db, user)
    db.commit()
    return MessageOut(message=GENERIC_REGISTER)


@router.post("/verify-email", response_model=MessageOut)
def verify_email(body: TokenIn, request: Request, db: Session = Depends(get_db)) -> MessageOut:
    enforce(f"verify:ip:{client_ip(request)}", limit=20, window_seconds=HOUR)
    tok = auth_tokens.consume(db, body.token, "verify_email")
    if tok is None:
        raise _err(400, "invalid_token", "Link inválido ou expirado. Solicite um novo e-mail de confirmação.")
    user = db.get(User, tok.user_id)
    assert user is not None
    if user.email_verified_at is None:
        user.email_verified_at = sessions.utcnow()
    db.commit()
    if user.status == "pending_approval":
        return MessageOut(message="E-mail confirmado! Sua conta aguarda a aprovação do administrador.")
    return MessageOut(message="E-mail confirmado! Você já pode entrar.")


@router.post("/resend-verification", response_model=MessageOut, status_code=202)
def resend_verification(body: EmailIn, request: Request, db: Session = Depends(get_db)) -> MessageOut:
    email = str(body.email).lower()
    enforce(f"resend:ip:{client_ip(request)}", limit=10, window_seconds=HOUR)
    enforce(f"resend:email:{email}", limit=3, window_seconds=HOUR)
    user = db.scalar(select(User).where(User.email == email))
    if user is not None and user.email_verified_at is None:
        _send_verification(db, user)
        db.commit()
    return MessageOut(message=GENERIC_REGISTER)


@router.post("/login", response_model=SessionOut | MfaChallengeOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    email = str(body.email).lower()
    enforce(f"login:ip:{ip}", limit=30, window_seconds=15 * 60)
    enforce(f"login:email:{email}", limit=5, window_seconds=15 * 60)

    user = db.scalar(select(User).where(User.email == email))
    ok = passwords.verify_password(user.password_hash if user else None, body.password)
    if not ok or user is None:
        if user is not None:
            audit.record(db, "login_failed", "failure", actor_id=user.id, ip=ip)
            db.commit()
        raise _err(401, "invalid_credentials", "E-mail ou senha incorretos.")

    # A partir daqui a senha está correta: podemos explicar o motivo do bloqueio.
    if user.email_verified_at is None:
        raise _err(403, "email_not_verified", "Confirme seu e-mail antes de entrar. Verifique sua caixa de entrada.")
    if user.status == "pending_approval":
        raise _err(403, "pending_approval", "Sua conta ainda aguarda a aprovação do administrador.")
    if user.status == "rejected":
        raise _err(403, "rejected", "Sua solicitação de cadastro não foi aprovada.")
    if user.status == "suspended":
        raise _err(403, "suspended", "Sua conta está suspensa. Fale com o administrador.")

    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(body.password)
    if user.mfa_enabled:
        # Senha correta, mas falta o segundo fator: nenhuma sessão é criada ainda.
        challenge = auth_tokens.issue(db, user.id, "mfa_challenge", timedelta(minutes=5))
        db.commit()
        return MfaChallengeOut(challenge=challenge)
    return _finish_login(db, user, request, response, mfa_verified=False)


def _finish_login(db: Session, user: User, request: Request, response: Response, mfa_verified: bool) -> SessionOut:
    ip = client_ip(request)
    user.last_login_at = sessions.utcnow()
    token = sessions.create_session(db, user, request.headers.get("user-agent"), ip, mfa_verified=mfa_verified)
    audit.record(db, "login", "success", actor_id=user.id, details={"mfa": mfa_verified}, ip=ip)
    db.commit()
    _set_session_cookie(response, token)
    return SessionOut(user=UserOut.model_validate(user), csrf_token=csrf_for_session(token))


@router.post("/login/mfa", response_model=SessionOut)
def login_mfa(body: MfaLoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> SessionOut:
    ip = client_ip(request)
    enforce(f"mfa:ip:{ip}", limit=20, window_seconds=15 * 60)
    tok = db.scalar(select(AuthToken).where(AuthToken.token_hash == hash_token(body.challenge),
                                            AuthToken.purpose == "mfa_challenge"))
    if tok is None or tok.used_at or tok.expires_at <= sessions.utcnow():
        raise _err(401, "invalid_challenge", "A verificação expirou. Entre novamente.")
    enforce(f"mfa:user:{tok.user_id}", limit=5, window_seconds=15 * 60)
    user = db.get(User, tok.user_id)
    assert user is not None
    step = mfa.check_code(mfa.decrypt(user.mfa_secret_enc or "") or "", body.code, user.mfa_last_step)
    if step is None:
        audit.record(db, "mfa_failed", "failure", actor_id=user.id, ip=ip)
        db.commit()
        raise _err(401, "invalid_code", "Código inválido. Confira o aplicativo autenticador.")
    if user.status != "active":
        raise _err(403, user.status, "Sua conta não está ativa.")
    tok.used_at = sessions.utcnow()
    user.mfa_last_step = step
    return _finish_login(db, user, request, response, mfa_verified=True)


@router.post("/reauth", response_model=MessageOut)
def reauth(body: ReauthIn, request: Request, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> MessageOut:
    """Confirma a identidade de novo (senha + código, quando houver MFA) para operações críticas."""
    enforce(f"reauth:user:{ctx.user.id}", limit=5, window_seconds=15 * 60)
    if not passwords.verify_password(ctx.user.password_hash, body.password):
        raise _err(400, "invalid_password", "Senha incorreta.")
    if ctx.user.mfa_enabled:
        step = mfa.check_code(mfa.decrypt(ctx.user.mfa_secret_enc or "") or "", body.code or "", ctx.user.mfa_last_step)
        if step is None:
            raise _err(400, "invalid_code", "Código inválido.")
        ctx.user.mfa_last_step = step
    ctx.session.reauth_at = sessions.utcnow()
    audit.record(db, "reauthenticated", "success", actor_id=ctx.user.id, ip=client_ip(request))
    db.commit()
    return MessageOut(message="Identidade confirmada.")


@router.post("/logout", response_model=MessageOut)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> MessageOut:
    token = request.cookies.get(session_cookie_name())
    if token and len(token) <= 100:
        sessions.revoke_token(db, token)
        db.commit()
    _clear_session_cookie(response)
    return MessageOut(message="Você saiu da sua conta.")


@router.get("/session", response_model=SessionOut)
def current_session(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> SessionOut:
    db.commit()  # grava last_seen_at
    return SessionOut(user=UserOut.model_validate(ctx.user), csrf_token=csrf_for_session(ctx.token))


@router.post("/forgot-password", response_model=MessageOut, status_code=202)
def forgot_password(body: EmailIn, request: Request, db: Session = Depends(get_db)) -> MessageOut:
    s = get_settings()
    email = str(body.email).lower()
    enforce(f"forgot:ip:{client_ip(request)}", limit=10, window_seconds=HOUR)
    enforce(f"forgot:email:{email}", limit=3, window_seconds=HOUR)
    user = db.scalar(select(User).where(User.email == email))
    if user is not None and user.status not in ("rejected",):
        token = auth_tokens.issue(db, user.id, "reset_password", timedelta(minutes=s.reset_token_minutes))
        link = f"{s.frontend_url}/redefinir-senha#token={token}"
        get_email_sender().send(
            user.email,
            "Redefinição de senha da CarteirIA",
            f"Recebemos um pedido para redefinir sua senha.\n\nAcesse: {link}\n\n"
            f"O link vale por {s.reset_token_minutes} minutos e pode ser usado uma única vez. "
            "Se você não pediu, ignore esta mensagem; sua senha continua a mesma.",
        )
        audit.record(db, "password_reset_requested", "success", actor_id=user.id, ip=client_ip(request))
        db.commit()
    return MessageOut(message=GENERIC_FORGOT)


@router.post("/reset-password", response_model=MessageOut)
def reset_password(body: ResetPasswordIn, request: Request, db: Session = Depends(get_db)) -> MessageOut:
    enforce(f"reset:ip:{client_ip(request)}", limit=10, window_seconds=HOUR)
    tok = auth_tokens.consume(db, body.token, "reset_password")
    if tok is None:
        raise _err(400, "invalid_token", "Link inválido ou expirado. Solicite uma nova redefinição.")
    user = db.get(User, tok.user_id)
    assert user is not None
    _check_password(body.password, user.email)
    user.password_hash = passwords.hash_password(body.password)
    if user.email_verified_at is None:
        user.email_verified_at = sessions.utcnow()  # o link provou a posse do e-mail
    sessions.revoke_all(db, user.id)
    audit.record(db, "password_reset", "success", actor_id=user.id, ip=client_ip(request))
    db.commit()
    return MessageOut(message="Senha redefinida. Entre com a nova senha.")


@router.post("/change-password", response_model=MessageOut)
def change_password(
    body: ChangePasswordIn,
    request: Request,
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> MessageOut:
    enforce(f"change-password:user:{ctx.user.id}", limit=5, window_seconds=15 * 60)
    if not passwords.verify_password(ctx.user.password_hash, body.current_password):
        raise _err(400, "invalid_password", "A senha atual está incorreta.")
    _check_password(body.new_password, ctx.user.email)
    ctx.user.password_hash = passwords.hash_password(body.new_password)
    sessions.revoke_all(db, ctx.user.id, except_id=ctx.session.id)
    audit.record(db, "password_changed", "success", actor_id=ctx.user.id, ip=client_ip(request))
    db.commit()
    get_email_sender().send(
        ctx.user.email,
        "Sua senha da CarteirIA foi alterada",
        "A senha da sua conta foi alterada. Se não foi você, redefina a senha imediatamente.",
    )
    return MessageOut(message="Senha alterada. As outras sessões foram encerradas.")
