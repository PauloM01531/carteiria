#!/bin/sh
# Executado apenas na primeira inicialização do volume do PostgreSQL.
# Cria dois papéis com privilégios mínimos:
#   - DB_OWNER_USER: dono do schema e das tabelas (migrações).
#   - DB_APP_USER:   usado pela API; NÃO é dono e NÃO tem BYPASSRLS, então o RLS vale para ele.
set -e

psql -v ON_ERROR_STOP=1 --username postgres <<-EOSQL
  CREATE ROLE ${DB_OWNER_USER} LOGIN PASSWORD '${DB_OWNER_PASSWORD}' NOSUPERUSER NOCREATEROLE NOCREATEDB NOBYPASSRLS;
  CREATE ROLE ${DB_APP_USER}   LOGIN PASSWORD '${DB_APP_PASSWORD}'   NOSUPERUSER NOCREATEROLE NOCREATEDB NOBYPASSRLS;
EOSQL

for DB in ${DB_NAME} ${DB_TEST_NAME}; do
  psql -v ON_ERROR_STOP=1 --username postgres <<-EOSQL
    CREATE DATABASE ${DB} OWNER ${DB_OWNER_USER};
    REVOKE ALL ON DATABASE ${DB} FROM PUBLIC;
    GRANT CONNECT ON DATABASE ${DB} TO ${DB_APP_USER};
EOSQL
  psql -v ON_ERROR_STOP=1 --username postgres --dbname ${DB} <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS citext;
    REVOKE ALL ON SCHEMA public FROM PUBLIC;
    ALTER SCHEMA public OWNER TO ${DB_OWNER_USER};
    GRANT USAGE ON SCHEMA public TO ${DB_APP_USER};
EOSQL
done
