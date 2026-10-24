#!/bin/sh
# Backup diário no SERVIDOR de produção. Agende no cron, ex.:
#   15 3 * * * cd /opt/carteiria && ./scripts/backup.sh >> /var/log/carteiria-backup.log 2>&1
# Requer: BACKUP_PASSPHRASE no ambiente (cifra o arquivo com AES-256 via openssl antes de guardar).
set -eu
cd "$(dirname "$0")/.."
KEEP_DAYS="${KEEP_DAYS:-14}"
DB_NAME="$(grep '^DB_NAME=' .env.production | cut -d= -f2)"
DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$DIR"
chmod 700 "$DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$DIR/$DB_NAME-$STAMP.dump.enc"
: "${BACKUP_PASSPHRASE:?defina BACKUP_PASSPHRASE}"

# pg_dump como superusuário (o RLS forçado esconderia as linhas do papel dono)
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U postgres -d "$DB_NAME" -Fc \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:BACKUP_PASSPHRASE -out "$OUT"
chmod 600 "$OUT"

# Verifica se o arquivo decifra e é legível
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$OUT" \
  | docker compose -f docker-compose.prod.yml exec -T db pg_restore --list > /dev/null

find "$DIR" -name "$DB_NAME-*.dump.enc" -mtime +"$KEEP_DAYS" -delete
echo "$(date -Is) backup ok: $OUT"
# Copie também para outro local (outro servidor/armazenamento), ex.: rclone copy "$OUT" remoto:carteiria-backups
