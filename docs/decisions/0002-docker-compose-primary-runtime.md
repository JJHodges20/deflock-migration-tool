# 0002 - Docker Compose is the primary runtime for the whole application

- **Status:** Accepted (confirmed requirement from the project owner, 2026-10-15)
- **Scope:** Denver pilot and all later releases unless superseded

## Requirement as confirmed by the owner

Docker Compose must be the primary way to run the entire application, not merely the database or routing engine.

- Containerize the frontend, backend, PostgreSQL/PostGIS, Valhalla, and the camera-update worker. Include any selected self-hosted geocoding and map-serving components in the Docker deployment as well.
- Run database migrations, initial data imports, and road-graph builds through containerized commands or setup jobs.
- Normal application use must not require separately installing Python, Node.js, PostgreSQL, or Valhalla on the host computer.
- Persist database contents and downloaded/built geographic data across normal container restarts. Never delete them during ordinary shutdown.
- Document first-time setup separately from everyday startup. After initialization, the intended startup command is `docker compose up`.
- Verify service readiness, persistence, restart behavior, and a complete browser-to-backend routing request before marking Docker setup complete.
- The existing M0 feasibility review and approval gates are preserved.

## Consequences for the implementation plan

1. **Host prerequisites shrink to Docker Desktop and Git.** Node.js is absent on the pilot machine (checked 2026-10-15); that is acceptable because the web image builds the frontend inside Docker. Host Python 3.14 is used only for optional development scripts, never for running the app.
2. **Images are pinned, never `latest`.** M0 pinned `ghcr.io/valhalla/valhalla:3.9.1` (release 2026-10-06). PostGIS, Nominatim, and the application base images will be pinned in M1 after the same kind of check.
3. **One-time jobs are Compose services with profiles**, for example `docker compose --profile setup run --rm graph-build`, `... run --rm camera-sync`, `... run --rm db-migrate`. Everyday `docker compose up` starts only long-running services and must not rebuild the graph or re-import data.
4. **Persistence uses named volumes**: `pgdata` (PostGIS), `valhalla_tiles` (built graph + config), `osm_extracts` (downloaded PBF and diffs), `geocoder_db` (if self-hosted Nominatim is approved), `basemap` (PMTiles archive). `docker compose down` without `-v` keeps them; the documentation must warn that `down -v` destroys them.
5. **Readiness is explicit**: healthchecks on PostGIS (`pg_isready`), Valhalla (`/status`), API (`/api/v1/health/data`), web (HTTP 200), and `depends_on: condition: service_healthy` so `docker compose up` converges without manual ordering.
6. **Memory budget is a real constraint.** Docker Desktop on the pilot machine is allocated about 8 GB (`docker info`, 2026-10-15) out of 16 GB physical. Graph builds, geocoder imports, and the running stack must fit this budget or the documentation must say exactly how to raise it. M0 measured the Valhalla build within this budget; see `docs/FEASIBILITY_REPORT.md`.
7. **Localhost binding stays mandatory.** Only the web entry point (and, during development, the API) is published, bound to `127.0.0.1`. PostGIS, Valhalla, and the geocoder are reachable only on the Compose network.
8. **The M1 gate adds Docker-specific proof**: `docker compose up` from a clean clone after the documented first-time setup, a readiness check for every service, a `docker compose restart` that keeps data, and one browser-to-backend routing request through the containers.

## What this decision does not change

- The M0 → M1 approval gate and the one-milestone-at-a-time rule.
- The prohibition on paid services, public deployment, or a third-party geocoder without explicit approval.
- The privacy rules: redacted logs and no persistent trip data apply inside containers exactly as before.
