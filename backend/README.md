# DeFlockMigration backend

FastAPI service, camera-sync worker, and Alembic migrations. It runs inside Docker Compose (see the repository README and `docs/USER_GUIDE.md`); host Python is only needed for optional local development.

Layout follows the roadmap: `api/` (routers, schemas, errors), `application/` (use cases), `domain/` (models and policies), `geospatial/`, `routing/` (Valhalla adapter and candidate selection), `geocoding/`, `data_sources/` (Overpass client), `ingestion/` (normalization, sync, promotion), `storage/` (SQLAlchemy models, repositories, migrations), `workers/` (sync loop, setup jobs), `core/` (settings, redacted logging, config loader, errors).

Tests: `tests/unit`, `tests/contract` (API with fake providers), `tests/privacy` (redaction), `tests/regression` (module boundaries), `tests/integration` (needs PostGIS; skipped without `DEFLOCK_DATABASE_URL`). Fixtures are labelled `fixture_*` and live only under `tests/fixtures/`.
