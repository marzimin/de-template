#!/usr/bin/env bash
set -euo pipefail

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  -v warehouse_db="$WAREHOUSE_DB" \
  -v warehouse_user="$WAREHOUSE_USER" \
  -v warehouse_password="$WAREHOUSE_PASSWORD" <<'SQL'
CREATE DATABASE airflow_db;
CREATE USER airflow WITH PASSWORD 'airflow';
ALTER DATABASE airflow_db OWNER TO airflow;
GRANT ALL PRIVILEGES ON DATABASE airflow_db TO airflow;

CREATE DATABASE :"warehouse_db";
CREATE USER :"warehouse_user" WITH PASSWORD :'warehouse_password';
GRANT ALL PRIVILEGES ON DATABASE :"warehouse_db" TO :"warehouse_user";
SQL

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$WAREHOUSE_DB" \
  -v warehouse_user="$WAREHOUSE_USER" <<'SQL'
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;

GRANT ALL PRIVILEGES ON SCHEMA raw, staging, marts TO :"warehouse_user";
SQL
