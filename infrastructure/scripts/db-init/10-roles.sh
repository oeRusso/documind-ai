#!/usr/bin/env bash
# Creates the two database roles and the test database. Idempotent.
#
#   migrator -> owns the schema and the tables; Alembic connects with it.
#   app      -> the API/workers role: only SELECT/INSERT/UPDATE/DELETE, can never bypass RLS.
#
# Runs automatically on the first start of the PostgreSQL container
# (/docker-entrypoint-initdb.d) and also by hand in CI, using standard PG* variables.
set -euo pipefail

: "${APP_DB_PASSWORD:?APP_DB_PASSWORD is required}"
: "${MIGRATOR_DB_PASSWORD:?MIGRATOR_DB_PASSWORD is required}"
SUPERUSER="${POSTGRES_USER:-postgres}"
MAIN_DB="${POSTGRES_DB:-documind}"
TEST_DB="${MAIN_DB}_test"

psql_admin() { psql -v ON_ERROR_STOP=1 --no-psqlrc --username "$SUPERUSER" "$@"; }

psql_admin --dbname postgres \
  -v app_pw="$APP_DB_PASSWORD" -v migrator_pw="$MIGRATOR_DB_PASSWORD" \
  -v main_db="$MAIN_DB" -v test_db="$TEST_DB" <<'SQL'
SELECT format('CREATE ROLE migrator LOGIN PASSWORD %L', :'migrator_pw')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'migrator') \gexec
SELECT format('CREATE ROLE app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %L', :'app_pw')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app') \gexec
SELECT format('CREATE DATABASE %I', :'test_db')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'test_db') \gexec
SQL

for db in "$MAIN_DB" "$TEST_DB"; do
  psql_admin --dbname "$db" -v db="$db" <<'SQL'
-- The database owner also owns the `public` schema (pg_database_owner, PostgreSQL 15+).
ALTER DATABASE :"db" OWNER TO migrator;
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE :"db" TO app;
GRANT USAGE ON SCHEMA public TO app;
-- Extensions need superuser; migrations only run CREATE EXTENSION IF NOT EXISTS (a no-op).
CREATE EXTENSION IF NOT EXISTS vector;
-- Every table/sequence migrator creates from now on is usable by app (DML only, no DDL).
ALTER DEFAULT PRIVILEGES FOR ROLE migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app;
ALTER DEFAULT PRIVILEGES FOR ROLE migrator IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO app;
SQL
done

echo "db-init: roles 'migrator' and 'app' ready on $MAIN_DB and $TEST_DB"
