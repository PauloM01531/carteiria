# API da CarteirIA (produção)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

# Executa sem privilégios de root
RUN useradd --system --uid 10001 carteiria && chown -R carteiria /app
USER carteiria

EXPOSE 8000
# --proxy-headers: o IP real vem do Caddy (único que alcança a API pela rede interna)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*", "--workers", "1", "--no-server-header"]
