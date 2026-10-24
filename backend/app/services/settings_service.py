from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSetting
from app.models.admin import REGISTRATION_MODES

DEFAULT_MODE = "approval"


def get_registration_mode(db: Session) -> str:
    value = db.scalar(select(AppSetting.value).where(AppSetting.key == "registration_mode"))
    return value if value in REGISTRATION_MODES else "closed"


def set_registration_mode(db: Session, mode: str) -> None:
    if mode not in REGISTRATION_MODES:
        raise ValueError("Modo inválido")
    row = db.get(AppSetting, "registration_mode")
    if row is None:  # a linha é criada pela migração; o papel da aplicação não insere aqui
        raise RuntimeError("Configuração ausente; execute as migrações.")
    row.value = mode
