-- Runs once, when the pgdata volume is first initialized. Creates the throwaway database used by
-- `docker compose --profile test run --rm api-tests`. The application database is POSTGRES_DB.
CREATE DATABASE deflock_test;
\connect deflock_test
CREATE EXTENSION IF NOT EXISTS postgis;
