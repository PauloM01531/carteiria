"""Hash de senhas com Argon2id (argon2-cffi). A senha nunca é armazenada em texto puro."""
import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # Argon2id com parâmetros recomendados pela biblioteca

# Hash fictício usado quando o e-mail não existe, para o tempo de resposta não revelar contas.
_DUMMY_HASH = _hasher.hash("senha-ficticia-para-tempo-constante")

MIN_LEN = 10
MAX_LEN = 128


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def password_problems(password: str, email: str | None = None) -> list[str]:
    """Regras de senha. Retorna a lista de problemas (vazia = senha aceita)."""
    problems: list[str] = []
    if len(password) < MIN_LEN:
        problems.append(f"A senha deve ter pelo menos {MIN_LEN} caracteres.")
    if len(password) > MAX_LEN:
        problems.append(f"A senha deve ter no máximo {MAX_LEN} caracteres.")
    if not re.search(r"[A-Za-zÀ-ÿ]", password) or not re.search(r"\d", password):
        problems.append("A senha deve conter letras e números.")
    if email and password.strip().lower() == email.strip().lower():
        problems.append("A senha não pode ser igual ao e-mail.")
    return problems
