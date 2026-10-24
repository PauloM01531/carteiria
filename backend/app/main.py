"""Aplicação FastAPI da CarteirIA."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import admin, auth, bills, cards, categories, health, me, planning, reports, transactions
from app.config import get_settings

log = logging.getLogger("carteiria")

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="CarteirIA API",
        version="0.1.0",
        # Documentação interativa apenas fora de produção.
        docs_url=None if s.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if s.is_production else "/api/openapi.json",
    )

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        # Bloqueia requisições que alteram dados vindas de outra origem (camada extra contra CSRF).
        origin = request.headers.get("origin")
        if request.method in UNSAFE and origin and origin not in s.allowed_origins:
            return JSONResponse(
                {"detail": {"code": "bad_origin", "message": "Origem não permitida."}}, status_code=403
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/docs"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if s.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        # Mostra quais campos falharam, sem ecoar os valores enviados (podem conter senhas).
        fields = []
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", []) if p != "body"]
            fields.append({"field": ".".join(loc), "message": err.get("msg", "inválido")})
        return JSONResponse(
            {"detail": {"code": "validation_error", "message": "Verifique os dados informados.", "fields": fields}},
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        detail = exc.detail
        if isinstance(detail, str):
            detail = {"code": "error", "message": detail}
        return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        # Registra o tipo do erro no servidor; o cliente recebe uma mensagem genérica.
        log.exception("Erro não tratado em %s %s", request.method, request.url.path)
        return JSONResponse(
            {"detail": {"code": "internal_error", "message": "Ocorreu um erro inesperado. Tente novamente."}},
            status_code=500,
        )

    for r in (health.router, auth.router, me.router, categories.router, transactions.router,
              cards.router, bills.router, reports.router, reports.dash, planning.router, admin.router):
        app.include_router(r, prefix="/api/v1")
    return app


app = create_app()
