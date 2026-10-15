# Self-hosted Nominatim M0 spike (2026-10-15)

Containerized import of the Geofabrik Colorado extract with `mediagis/nominatim:5.3.2`, queried only with public landmarks and public office addresses. Nothing here calls the public Nominatim service.

## Run

```
docker volume create deflock_nominatim_spike_db
docker run -d --name deflock-nominatim-spike -p 127.0.0.1:8081:8080 --shm-size=1g \
  -e PBF_PATH=/pbf/colorado-latest.osm.pbf -e IMPORT_STYLE=full -e THREADS=8 \
  -e IMPORT_WIKIPEDIA=false -e IMPORT_US_POSTCODES=false -e IMPORT_TIGER_ADDRESSES=false \
  -e NOMINATIM_PASSWORD=<local secret> \
  -e POSTGRES_SHARED_BUFFERS=1GB -e POSTGRES_MAINTENANCE_WORK_MEM=1GB \
  -e POSTGRES_EFFECTIVE_CACHE_SIZE=3GB -e POSTGRES_WORK_MEM=32MB -e POSTGRES_AUTOVACUUM_WORK_MEM=512MB \
  -v deflock_nominatim_spike_db:/var/lib/postgresql/16/main \
  -v "<project>/data/raw/osm:/pbf:ro" mediagis/nominatim:5.3.2
python -I spikes/nominatim/test_queries.py --base http://127.0.0.1:8081 --label 2026-10-15
```

Lesson: the image's entrypoint runs `chown -R` on `/nominatim`, so a read-only mount under that path aborts the container. Mount the extract elsewhere (here `/pbf`).

## Measurements

| Item | Value |
|---|---|
| Container start to API ready | 16 min 55 s (20:42:52Z to 20:59:47Z) |
| osm2pgsql load | 299 s |
| Peak container memory (60 s samples) | 5.19 GiB |
| Database volume after import | 9.77 GB |
| Data timestamp reported by `/status` | 2026-10-14T20:20:43Z |
| Warm query latency | 16 to 61 ms |

## Query results (top hit)

| Query | Top result |
|---|---|
| Union Station, Denver, CO | Union Station, 1701 Wynkoop Street (tourism) |
| Denver Zoo | Denver Zoo, 2300 Steele Street |
| Colorado State Capitol, Denver | Colorado State Capitol Annex Building (ranking quirk) |
| Denver International Airport | Denver International Airport, 8500 Peña Boulevard |
| Red Rocks Amphitheatre | Red Rocks Amphitheatre, Morrison |
| 1437 Bannock St, Denver, CO | Denver City & County Building |
| 200 E Colfax Ave, Denver, CO 80203 | feature at the Capitol grounds |
| 1701 Wynkoop St, Denver, CO | The Crawford Hotel (Union Station building) |
| 2300 Steele St, Denver, CO | Denver Zoo |
| Washington Park, Denver | Washington Park |
| Glendale, Colorado | South Colorado Boulevard, Glendale (road before municipality) |
| Nonexistent Street 99999, Denver | no results |
| reverse 39.7393, -104.9848 | Capitol-grounds feature, 200 East Colfax Avenue |
| reverse 39.8494, -104.6737 | 8500 Peña Boulevard |

Full payloads: `queries_2026-10-15.json`. House numbers resolve only where OSM has a feature carrying that address; TIGER interpolation data was not imported.
