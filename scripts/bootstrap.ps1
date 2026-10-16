<#
.SYNOPSIS
  First-time setup for DeFlockMigration on Windows. Run once from a clean clone.
  Everyday startup afterwards is simply:  docker compose up

.DESCRIPTION
  Requires only Docker Desktop (with Compose v2) and Git. Builds the images, applies database
  migrations, downloads the public Colorado extract, builds the routing graph, extracts the basemap,
  publishes the first camera snapshot, starts the self-hosted geocoder import, starts the stack, and
  runs the smoke test. Every step is a containerized job; nothing is installed on the host.

.PARAMETER SkipGeocoder
  Do not start the geocoder import (address search stays "not configured" until it runs).
.PARAMETER SkipBuild
  Reuse already built images.
#>
[CmdletBinding()]
param(
  [switch]$SkipGeocoder,
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$total = [System.Diagnostics.Stopwatch]::StartNew()

function Invoke-Step {
  param([string]$Name, [scriptblock]$Action)
  Write-Host ""
  Write-Host ("=== " + $Name + " ===") -ForegroundColor Cyan
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  $global:LASTEXITCODE = 0
  & $Action
  if ($LASTEXITCODE -ne 0) { throw ("Step failed: " + $Name + " (exit code " + $LASTEXITCODE + ")") }
  Write-Host ("=== done: {0} in {1:n0} s" -f $Name, $sw.Elapsed.TotalSeconds) -ForegroundColor Green
}

Invoke-Step "Check Docker Desktop" {
  docker version --format '{{.Server.Version}}' | Out-Null
  docker compose version | Out-Null
}

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env from .env.example." -ForegroundColor Yellow
}
$envText = Get-Content ".env" -Raw
if ($envText -match "change-me-local-only") {
  $chars = [char[]]"abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
  $rng = New-Object System.Random
  $make = { -join (1..28 | ForEach-Object { $chars[$rng.Next(0, $chars.Length)] }) }
  $envText = $envText -replace "POSTGRES_PASSWORD=change-me-local-only", ("POSTGRES_PASSWORD=" + (& $make))
  $envText = $envText -replace "NOMINATIM_PASSWORD=change-me-local-only", ("NOMINATIM_PASSWORD=" + (& $make))
  Set-Content -Path ".env" -Value $envText -Encoding ascii
  Write-Host "Generated local-only passwords in .env (never committed)." -ForegroundColor Yellow
}

if (-not $SkipBuild) {
  Invoke-Step "Build application images" { docker compose build }
}
Invoke-Step "Apply database migrations" { docker compose --profile setup run --rm db-migrate }
Invoke-Step "Download the Colorado OSM extract (about 385 MB, checksum verified)" { docker compose --profile setup run --rm osm-download }
Invoke-Step "Build the routing graph inside the Valhalla container" { docker compose --profile setup run --rm graph-build }
Invoke-Step "Extract the Denver basemap (about 90 MB)" { docker compose --profile setup run --rm basemap-extract }
Invoke-Step "Download basemap fonts and sprites" { docker compose --profile setup run --rm basemap-assets }
Invoke-Step "Publish the first camera snapshot (one bounded Overpass query)" { docker compose --profile setup run --rm camera-sync-once }

if ($SkipGeocoder) {
  # The geocoder is a default service; scale it to zero for this run only. A later `docker compose up`
  # starts it (and its one-time import) as usual.
  Invoke-Step "Start the application (geocoder skipped for this run)" { docker compose up -d --scale geocoder=0 }
} else {
  Invoke-Step "Start the self-hosted geocoder (first start imports Colorado; about 17 minutes in the background)" { docker compose up -d geocoder }
  Invoke-Step "Start the application" { docker compose up -d }
}
Invoke-Step "Smoke test" { & (Join-Path $PSScriptRoot "smoke_test.ps1") }

$port = 3000
$portMatch = Select-String -Path ".env" -Pattern '^\s*DEFLOCK_PORT\s*=\s*(\d+)' | Select-Object -First 1
if ($portMatch) { $port = [int]$portMatch.Matches[0].Groups[1].Value }
Write-Host ""
Write-Host ("Setup complete in {0:n0} s. Open http://127.0.0.1:{1}" -f $total.Elapsed.TotalSeconds, $port) -ForegroundColor Green
Write-Host "Everyday startup from now on:  docker compose up      (stop with Ctrl+C or: docker compose down)"
Write-Host "Address search becomes available once the geocoder import finishes (docker compose logs -f geocoder)."
