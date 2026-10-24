"""Tokens aleatórios. O banco guarda apenas o SHA-256; o valor original só existe no
cookie/e-mail do usuário. Como os tokens têm 256 bits de entropia, SHA-256 é suficiente."""
import hashlib
import hmac
import secrets

from app.config import get_settings


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def csrf_for_session(session_token: str) -> str:
    """Token CSRF derivado da sessão (HMAC). Um site externo não consegue calculá-lo."""
    key = get_settings().secret_key.encode("utf-8")
    return hmac.new(key, b"csrf:" + session_token.encode("utf-8"), hashlib.sha256).hexdigest()


def safe_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
