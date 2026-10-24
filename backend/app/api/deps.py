"""Dependências de autenticação e autorização usadas por todas as rotas protegidas.

Regras:
- A identidade vem SOMENTE do cookie de sessão validado no banco.
- Métodos que alteram dados exigem o cabeçalho X-CSRF-Token correto.
- Após validar, o id do usuário é aplicado ao RLS da transação.
"""
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db, set_rls_user
from app.models import User, UserSession
from app.security.tokens import csrf_for_session, safe_equals
from app.services import audit
from app.services.sessions import find_valid_session, revoke_all, touch

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def session_cookie_name() -> str:
    # O prefixo __Host- exige Secure, Path=/ e ausência de Domain (mais proteção em produção).
    return "__Host-cw_session" if get_settings().cookie_secure else "cw_session"


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@dataclass
class AuthContext:
    user: User
    session: UserSession
    token: str


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        {"code": "not_authenticated", "message": "Sessão inválida ou expirada. Entre novamente."},
    )


def get_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    token = request.cookies.get(session_cookie_name())
    if not token or len(token) > 100:
        raise _unauthorized()
    sess = find_valid_session(db, token)
    if sess is None:
        raise _unauthorized()
    user = sess.user
    if user.status != "active" or user.email_verified_at is None:
        revoke_all(db, user.id)
        db.commit()
        raise _unauthorized()
    if request.method not in SAFE_METHODS:
        sent = request.headers.get("x-csrf-token", "")
        if not sent or not safe_equals(sent, csrf_for_session(token)):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                {"code": "csrf", "message": "Requisição bloqueada por segurança. Recarregue a página."},
            )
    touch(db, sess)
    set_rls_user(db, user.id)
    return AuthContext(user=user, session=sess, token=token)


def require_admin(
    request: Request, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
) -> AuthContext:
    if ctx.user.role != "ADMIN":
        audit.record(
            db,
            "admin_access_denied",
            "denied",
            actor_id=ctx.user.id,
            details={"path": request.url.path, "method": request.method},
            ip=client_ip(request),
        )
        db.commit()
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, {"code": "forbidden", "message": "Acesso não permitido."}
        )
    return ctx
