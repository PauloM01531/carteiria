#!/bin/sh
# Restaura um backup cifrado em um banco NOVO (não sobrescreve o principal).
# Uso: BACKUP_PASSPHRASE=... ./scripts/restore.sh backups/carteiria-AAAAMMDD-HHMMSS.dump.enc [carteiria_restaurado]
set -eu
cd "$(dirname "$0")/.."
FILE="$1"
TARGET="${2:-carteiria_restaurado}"
case "$TARGET" in *[!a-z0-9_]*) echo "nome inválido"; exit 1;; esac
OWNER="$(grep '^DB_OWNER_USER=' .env.production | cut -d= -f2)"
APP="$(grep '^DB_APP_USER=' .env.production | cut -d= -f2)"
DC="docker compose -f docker-compose.prod.yml exec -T db"
$DC psql -U postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $TARGET"
$DC psql -U postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $TARGET OWNER $OWNER"
$DC psql -U postgres -v ON_ERROR_STOP=1 -c "REVOKE ALL ON DATABASE $TARGET FROM PUBLIC; GRANT CONNECT ON DATABASE $TARGET TO $APP"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$FILE" \
  | $DC pg_restore -U postgres -d "$TARGET" --exit-on-error
echo "Usuários: $($DC psql -U postgres -d "$TARGET" -tAc 'SELECT count(*) FROM users')"
echo "Restaurado em $TARGET. Confira e, com a API parada, troque DB_NAME no .env.production."
