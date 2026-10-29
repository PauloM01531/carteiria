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
    # Credenciais do papel DONO: só migrações e comandos administrativos do servidor precisam delas.
    # Em produção a API roda sem elas (menor privilégio).
    db_owner_user: str = "carteiria_owner"
    db_owner_password: str | None = None
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
        if not self.db_owner_password:
            raise RuntimeError(
                "Credenciais do papel dono ausentes. Rode migrações e comandos administrativos pelo "
                "serviço 'migrate' (docker compose -f docker-compose.prod.yml run --rm migrate ...)."
            )
        return self._url(self.db_owner_user, self.db_owner_password)


def check_production(s: Settings) -> list[str]:
    """Problemas de configuração que impedem rodar em produção com segurança."""
    problems = []
    if not s.cookie_secure:
        problems.append("COOKIE_SECURE deve ser true (HTTPS).")
    if len(s.secret_key) < 32 or "gere-um-valor" in s.secret_key:
        problems.append("SECRET_KEY ausente, curta ou com o valor de exemplo.")
    if not s.frontend_url.startswith("https://"):
        problems.append("FRONTEND_URL deve ser o endereço público com https://.")
    if not s.allowed_origins or any(not o.startswith("https://") for o in s.allowed_origins):
        problems.append("FRONTEND_ORIGINS deve conter só endereços https://.")
    if s.smtp_host in ("", "localhost", "127.0.0.1"):
        problems.append("SMTP_HOST deve apontar para um provedor de e-mail real.")
    weak = ("troque-esta-senha", "senha", "password", "123456")
    if len(s.db_app_password) < 20 or any(w in s.db_app_password.lower() for w in weak):
        problems.append("DB_APP_PASSWORD fraca ou com o valor de exemplo.")
    return problems


@lru_cache
def get_settings() -> Settings:
    s = Settings()  # type: ignore[call-arg]
    if s.is_production:
        problems = check_production(s)
        if problems:
            raise RuntimeError("Configuração de produção insegura: " + " ".join(problems))
    return s
