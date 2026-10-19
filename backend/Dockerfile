# DeFlockMigration backend image (API, camera-sync worker, setup jobs, migrations, tests).
# Build context is the repository root so configs and boundary files are baked in.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEFLOCK_PROJECT_ROOT=/app

WORKDIR /app/backend

# Dependencies first for layer caching.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt

# Application code, migrations, and tests.
COPY backend/pyproject.toml backend/README.md backend/alembic.ini /app/backend/
COPY backend/src /app/backend/src
COPY backend/alembic /app/backend/alembic
COPY backend/tests /app/backend/tests
RUN pip install --no-deps /app/backend

# Region configuration and public boundary data.
COPY configs /app/configs
COPY data/boundaries/denver_service_boundary_v1.geojson data/boundaries/denver_camera_envelope_v1.geojson data/boundaries/colorado_service_boundary_v1.geojson data/boundaries/colorado_camera_envelope_v1.geojson /app/data/boundaries/
COPY data/raw/overpass/denver_alpr_envelope_query.overpassql data/raw/overpass/colorado_alpr_envelope_query.overpassql /app/data/raw/overpass/
COPY data/fixtures/pilot_trips.json /app/data/fixtures/

RUN useradd --system --uid 10001 --create-home deflock \
    && mkdir -p /var/lib/deflock/snapshots \
    && chown -R deflock:deflock /var/lib/deflock /app/backend
USER deflock

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "deflockmigration.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "*"]
