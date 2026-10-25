#!/bin/sh
# Runs once, on a new development volume, as the database administrator.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=app_user="$DB_USER" --set=app_password="$DB_PASSWORD" \
  --set=test_user="$DB_TEST_USER" --set=test_password="$DB_TEST_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L',
              :'app_user', :'app_password') \gexec
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER CREATEDB NOCREATEROLE PASSWORD %L',
              :'test_user', :'test_password') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_user') \gexec
SELECT format('GRANT ALL ON SCHEMA public TO %I', :'app_user') \gexec
CREATE EXTENSION IF NOT EXISTS postgis;
SQL

# New pytest databases inherit PostGIS without granting superuser to test/runtime roles.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname template1 \
  --command='CREATE EXTENSION IF NOT EXISTS postgis;'
