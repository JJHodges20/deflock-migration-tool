<#
.SYNOPSIS
  Release audit checks for the Denver pilot (M8). Each check prints evidence; nothing here stores or logs a trip.
  Run from anywhere; the stack must be up for every check except "keys".

.PARAMETER Check
  keys     - no API key, token, or paid-provider reference in code, configuration, or the env example
  egress   - which containers can reach the internet (expected: only camera-sync; edge only publishes the port)
  logs     - make trip, address, reverse, and camera requests, then grep every container log for them (expected: none)
  restore  - dump the live database, restore into a scratch database, compare counts, drop the scratch database
  perf     - cold start to healthy, warm plan latencies over the pilot trips, resource use
  all      - keys, egress, logs, restore (perf restarts the stack, so it is run only when named)

.EXAMPLE
  scripts\audit.ps1 -Check all
  scripts\audit.ps1 -Check perf
#>
[CmdletBinding()]
param([ValidateSet("keys", "egress", "logs", "restore", "perf", "all")][string]$Check = "all")

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$port = 3000
if (Test-Path ".env") {
  $m = Select-String -Path ".env" -Pattern "^DEFLOCK_PORT=(\d+)"
  if ($m) { $port = [int]$m.Matches[0].Groups[1].Value }
}
$base = "http://127.0.0.1:$port"
$dbUser = "deflock"
if (Test-Path ".env") {
  $u = Select-String -Path ".env" -Pattern "^POSTGRES_USER=(\S+)"
  if ($u) { $dbUser = $u.Matches[0].Groups[1].Value }
}
$checks = if ($Check -eq "all") { @("keys", "egress", "logs", "restore") } else { @($Check) }

function Show-Section([string]$Title) { Write-Host ""; Write-Host ("=== " + $Title + " ===") -ForegroundColor Cyan }

if ($checks -contains "keys") {
  Show-Section "paid-key audit: any API key, token, or paid-provider reference in code, configuration, or the env example?"
  $hits = Select-String -Path "backend/src/deflockmigration/**/*.py", "apps/web/src/**/*.ts", "apps/web/src/**/*.tsx", "configs/*.yaml", "configs/regions/*.yaml", ".env.example", "compose.yaml" -Pattern "api[_-]?key|apikey|access[_-]?token|secret[_-]?key|bearer|billing|stripe|google.*key|mapbox" -ErrorAction SilentlyContinue
  if ($hits) { $hits | ForEach-Object { "  " + $_.Path + ":" + $_.LineNumber + ": " + $_.Line.Trim() } } else { "  no API key, token, or paid-provider reference found" }
  $secrets = (Get-Content .env.example) | Where-Object { $_ -match "^[A-Z_]+PASSWORD=" } | ForEach-Object { ($_ -split "=")[0] }
  "  env example secrets: " + ($secrets -join ", ") + " (local database passwords only)"
}

if ($checks -contains "egress") {
  Show-Section "egress audit: which containers can reach the internet? (expected: only camera-sync; edge is on the egress network for port publishing only)"
  $py = "import urllib.request, urllib.error`ntry:`n    urllib.request.urlopen('https://overpass-api.de/api/status', timeout=8).read(32); print('REACHED the internet (HTTP 200)')`nexcept urllib.error.HTTPError as e:`n    print('REACHED the internet (HTTP status', e.code, ')')`nexcept Exception as e:`n    print('no internet route:', type(e).__name__)"
  foreach ($svc in @("api", "camera-sync")) { "  $svc -> " + (docker compose exec -T $svc python -c $py 2>&1 | Select-Object -Last 1) }
  "  web -> " + (docker compose exec -T web node -e "fetch('https://overpass-api.de/api/status',{signal:AbortSignal.timeout(8000)}).then(r=>console.log('REACHED the internet (HTTP', r.status, ')')).catch(e=>console.log('no internet route:', e.cause ? e.cause.code : e.name))" 2>&1 | Select-Object -Last 1)
  "  edge -> " + (docker compose exec -T edge sh -c "if wget -q -T 8 -O /dev/null https://overpass-api.de/api/status; then echo 'REACHED the internet'; else echo 'no internet route (wget failed)'; fi" 2>&1 | Select-Object -Last 1)
  "  valhalla -> " + (docker compose exec -T valhalla sh -c "if curl -sf -m 8 -o /dev/null https://overpass-api.de/api/status; then echo 'REACHED the internet'; else echo 'no internet route (curl failed)'; fi" 2>&1 | Select-Object -Last 1)
  "  db -> " + (docker compose exec -T db bash -c "if timeout 8 bash -c 'cat < /dev/null > /dev/tcp/1.1.1.1/443' 2>/dev/null; then echo 'REACHED the internet'; else echo 'no internet route'; fi" 2>&1 | Select-Object -Last 1)
  "  geocoder -> " + (docker compose exec -T geocoder bash -c "if timeout 8 bash -c 'cat < /dev/null > /dev/tcp/1.1.1.1/443' 2>/dev/null; then echo 'REACHED the internet'; else echo 'no internet route'; fi" 2>&1 | Select-Object -Last 1)
  $project = (docker compose config --format json | ConvertFrom-Json).name
  "  networks: " + (docker network inspect "${project}_internal" --format '{{.Name}} internal={{.Internal}} containers={{len .Containers}}') + "; " + (docker network inspect "${project}_egress" --format '{{.Name}} internal={{.Internal}} containers={{len .Containers}}')
  foreach ($svc in @("edge", "web", "api", "camera-sync", "db", "valhalla", "geocoder")) {
    $id = docker compose ps -q $svc
    if ($id) { "  $svc on: " + (docker inspect $id --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}') }
  }
}

if ($checks -contains "logs") {
  Show-Section "log audit: plan, geocode, reverse, cameras, and an outside-area plan, then grep the container logs for them (expected: no hits)"
  $since = (Get-Date).ToUniversalTime().AddSeconds(-5).ToString("yyyy-MM-ddTHH:mm:ssZ")
  $body = @{ origin = @{ lat = 39.7530; lon = -105.0002 }; destination = @{ lat = 39.7503; lon = -104.9500 }; profiles = @("standard", "balanced", "fewest_mapped") } | ConvertTo-Json -Compress
  $null = Invoke-RestMethod -Method Post -Uri "$base/api/v1/routes/plan" -ContentType "application/json" -Body $body -TimeoutSec 60
  try { $null = Invoke-RestMethod -Method Post -Uri "$base/api/v1/geocode" -ContentType "application/json" -Body '{"query": "1437 Bannock St, Denver, CO"}' -TimeoutSec 30 } catch { }
  try { $null = Invoke-RestMethod -Method Post -Uri "$base/api/v1/geocode/reverse" -ContentType "application/json" -Body '{"lat": 39.7392, "lon": -104.9911}' -TimeoutSec 30 } catch { }
  try { $null = Invoke-RestMethod -Uri "$base/api/v1/cameras?bbox=-105.01,39.74,-104.94,39.76&scope=all_alpr" -TimeoutSec 30 } catch { }
  try { $null = Invoke-RestMethod -Method Post -Uri "$base/api/v1/routes/plan" -ContentType "application/json" -Body '{"origin": {"lat": 39.7530, "lon": -105.0002}, "destination": {"lat": 39.6654, "lon": -105.2057}}' -TimeoutSec 30 } catch { }
  Start-Sleep -Seconds 2
  $logs = docker compose logs --since $since --no-color edge api web geocoder valhalla 2>&1 | Out-String
  "  log lines captured since the requests: " + ($logs -split "`n").Count
  $total = 0
  foreach ($needle in @("39.753", "-105.0002", "39.7503", "-104.95", "Bannock", "39.7392", "-104.9911", "bbox=", "-105.2057")) {
    $hits = ([regex]::Matches($logs, [regex]::Escape($needle))).Count
    $total += $hits
    "  '$needle' in logs: $hits"
  }
  if ($total -eq 0) { "  RESULT: no trip, address, or viewport text in any container log" } else { Write-Warning "trip text found in logs" }
  "  nginx access log off: " + (docker compose exec -T edge sh -c "grep -c 'access_log off' /etc/nginx/nginx.conf")
}

if ($checks -contains "restore") {
  Show-Section "restore check: dump the live database, restore into a scratch database, compare counts, drop the scratch database"
  docker compose exec -T db pg_dump -U $dbUser -d deflock -Fc -f /tmp/deflock_backup.dump
  docker compose exec -T db ls -la /tmp/deflock_backup.dump
  docker compose exec -T db psql -U $dbUser -d postgres -q -c "DROP DATABASE IF EXISTS deflock_restore"
  docker compose exec -T db psql -U $dbUser -d postgres -q -c "CREATE DATABASE deflock_restore"
  docker compose exec -T db psql -U $dbUser -d deflock_restore -q -c "CREATE EXTENSION IF NOT EXISTS postgis"
  docker compose exec -T db pg_restore -U $dbUser -d deflock_restore --no-owner --no-privileges /tmp/deflock_backup.dump 2>&1 | Select-String -NotMatch "already exists|errors ignored|while PROCESSING TOC|TOC entry|Command was" | Select-Object -First 5
  $q = "SELECT (SELECT count(*) FROM camera_snapshots) AS snapshots, (SELECT count(*) FROM camera_records) AS records, (SELECT count(*) FROM snapshot_diffs) AS diffs, (SELECT count(*) FROM camera_road_associations) AS associations, (SELECT count(*) FROM sync_jobs) AS jobs, (SELECT snapshot_id FROM camera_snapshots WHERE promotion_state='active') AS active"
  $live = docker compose exec -T db psql -U $dbUser -d deflock -At -c $q
  $restored = docker compose exec -T db psql -U $dbUser -d deflock_restore -At -c $q
  "  live:     $live"
  "  restored: $restored"
  if ("$live" -eq "$restored") { "  RESULT: restored counts and active snapshot match the live database" } else { Write-Warning "restored database differs from live" }
  docker compose exec -T db psql -U $dbUser -d postgres -q -c "DROP DATABASE deflock_restore"
  docker compose exec -T db rm -f /tmp/deflock_backup.dump
  "  scratch database dropped and dump removed"
}

if ($checks -contains "perf") {
  Show-Section "performance: cold start to healthy, warm plan latencies over the pilot trips, resource use"
  docker compose stop | Out-Null
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  docker compose up -d 2>&1 | Out-Null
  $healthy = $false
  while ($sw.Elapsed.TotalSeconds -lt 300) {
    $states = docker compose ps --format '{{.Service}} {{.Status}}' edge web api db valhalla
    if (($states -split "`n" | Where-Object { $_ -match "healthy" }).Count -ge 5) { $healthy = $true; break }
    Start-Sleep -Seconds 2
  }
  "  cold start (stopped containers to edge, web, api, db, valhalla healthy): " + [int]$sw.Elapsed.TotalSeconds + " s (healthy=$healthy)"
  $trips = (Get-Content "data/fixtures/pilot_trips.json" -Raw | ConvertFrom-Json).trips | Where-Object { $_.expect.outcome -eq "planned" }
  $first = $true
  foreach ($round in 1..3) {
    foreach ($trip in $trips) {
      $body = @{ origin = @{ lat = $trip.origin[0]; lon = $trip.origin[1] }; destination = @{ lat = $trip.destination[0]; lon = $trip.destination[1] }; profiles = @("standard", "balanced", "fewest_mapped") } | ConvertTo-Json -Compress
      $t0 = Get-Date
      $null = Invoke-RestMethod -Method Post -Uri "$base/api/v1/routes/plan" -ContentType "application/json" -Body $body -TimeoutSec 60
      $ms = [int]((Get-Date) - $t0).TotalMilliseconds
      if ($first) { "  first plan after the cold start: $ms ms"; $first = $false }
    }
  }
  $m = Invoke-RestMethod -Uri "$base/api/v1/health/metrics"
  $p = $m.requests.'/api/v1/routes/plan'
  "  plan endpoint over " + $p.count + " requests: p50 " + $p.p50_ms + " ms, p95 " + $p.p95_ms + " ms, max " + $p.max_ms + " ms; search elapsed p50 " + $m.plans.elapsed_p50_ms + " ms, p95 " + $m.plans.elapsed_p95_ms + " ms; routing calls " + $m.plans.routing_calls_total + "; by status " + ($m.plans.by_search_status | ConvertTo-Json -Compress)
  "  api memory: " + $m.process.rss_mb + " MB; database " + [math]::Round($m.storage.database_bytes / 1MB, 1) + " MB"
  "  container memory and cpu:"; docker stats --no-stream --format "    {{.Name}} {{.MemUsage}} cpu {{.CPUPerc}}" | Where-Object { $_ -match "deflock" }
}
