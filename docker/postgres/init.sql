-- Create separate databases
CREATE DATABASE airflow_db;
CREATE DATABASE warehouse;

-- Create Airflow's dedicated Postgres user.
-- On Postgres 15+, GRANT ON DATABASE does NOT allow creating tables in the
-- `public` schema, so `airflow db migrate` would fail. Making airflow the
-- database owner gives it full control of that schema.
CREATE USER airflow WITH PASSWORD 'airflow';
ALTER DATABASE airflow_db OWNER TO airflow;
GRANT ALL PRIVILEGES ON DATABASE airflow_db TO airflow;

-- Connect to warehouse and create ELT schemas
\c warehouse;
CREATE SCHEMA IF NOT EXISTS raw;        -- Landing zone for API data
CREATE SCHEMA IF NOT EXISTS staging;    -- dbt staging models
CREATE SCHEMA IF NOT EXISTS marts;      -- dbt final models

-- Create a dedicated app user
CREATE USER de_user WITH PASSWORD 'de_password';
GRANT ALL PRIVILEGES ON DATABASE warehouse TO de_user;
GRANT ALL PRIVILEGES ON SCHEMA raw, staging, marts TO de_user;
