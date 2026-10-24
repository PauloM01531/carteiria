"""Configuração lida de variáveis de ambiente (arquivo .env na raiz do projeto)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    environment: str = "development"
    secret_key: str

    db_host: str = "localhost"
    db_port: int = 5433
    db_name: str = "carteiria"
    db_test_name: str = "carteiria_test"
    db_owner_user: str
    db_owner_password: str
    db_app_user: str
    db_app_password: str

    frontend_origins: str = "http://localhost:5173"
    frontend_url: str = "http://localhost:5173"
    cookie_secure: bool = False
    session_idle_minutes: int = 60
    session_absolute_hours: int = 12

    email_token_hours: int = 24
    reset_token_minutes: int = 30
    invite_days: int = 7

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    mail_from: str = "CarteirIA <nao-responda@carteiria.local>"

    # Usado somente pelos testes (limpeza do banco de testes) e por backups.
    postgres_superuser_password: str | None = None

    # Quando definido (testes), substitui o nome do banco.
    db_name_override: str | None = None

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]

    def _url(self, user: str, password: str) -> str:
        from urllib.parse import quote

        name = self.db_name_override or self.db_name
        return (
            f"postgresql+psycopg://{quote(user)}:{quote(password)}"
            f"@{self.db_host}:{self.db_port}/{name}"
        )

    @property
    def app_database_url(self) -> str:
        return self._url(self.db_app_user, self.db_app_password)

    @property
    def owner_database_url(self) -> str:
        return self._url(self.db_owner_user, self.db_owner_password)


@lru_cache
def get_settings() -> Settings:
    s = Settings()  # type: ignore[call-arg]
    if s.is_production:
        if not s.cookie_secure:
            raise RuntimeError("Em produção COOKIE_SECURE deve ser true (HTTPS).")
        if len(s.secret_key) < 32:
            raise RuntimeError("SECRET_KEY muito curta para produção.")
    return s
