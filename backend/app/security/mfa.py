"""Autenticação em dois fatores por aplicativo autenticador (TOTP, RFC 6238).

- O segredo é cifrado com Fernet (AES + HMAC) usando chave derivada da SECRET_KEY.
- Cada código só pode ser usado uma vez (guardamos o último passo de 30 s aceito).
- Aceita um passo de tolerância para diferença de relógio.
"""
import base64
import hashlib
import time

import pyotp
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

ISSUER = "CarteirIA"
STEP = 30


def _fernet() -> Fernet:
    key = hashlib.sha256(b"carteiria-mfa:" + get_settings().secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def new_secret() -> str:
    return pyotp.random_base32()


def encrypt(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def check_code(secret: str, code: str, last_step: int | None, now: float | None = None) -> int | None:
    """Retorna o passo aceito (para gravar e impedir reutilização) ou None se o código for inválido."""
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return None
    now = time.time() if now is None else now
    totp = pyotp.TOTP(secret)
    current = int(now // STEP)
    for step in (current - 1, current, current + 1):
        if totp.at(step * STEP) == code:
            if last_step is not None and step <= last_step:
                return None  # código já usado
            return step
    return None
