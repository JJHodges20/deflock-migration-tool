<#
.SYNOPSIS
  Refresh the public road data: download the latest Geofabrik Colorado extract (checksum verified)
  and rebuild the routing graph in a staging directory, then restart the routing service.
  The active graph is replaced only after the new build completes.

.PARAMETER Force
  Rebuild even if the extract has not changed.
#>
[CmdletBinding()]
param([switch]$Force)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$sw = [System.Diagnostics.Stopwatch]::StartNew()

Write-Host "Downloading the extract..." -ForegroundColor Cyan
docker compose --profile setup run --rm osm-download
if ($LASTEXITCODE -ne 0) { throw "extract download failed" }

Write-Host "Building the routing graph (about 2 to 3 minutes on the pilot machine)..." -ForegroundColor Cyan
if ($Force) { $env:GRAPH_FORCE_REBUILD = "1" }
docker compose --profile setup run --rm graph-build
$rc = $LASTEXITCODE
Remove-Item Env:GRAPH_FORCE_REBUILD -ErrorAction SilentlyContinue
if ($rc -ne 0) { throw "graph build failed; the previous graph is still active" }

Write-Host "Restarting the routing service to load the new graph..." -ForegroundColor Cyan
docker compose restart valhalla | Out-Null

# Validate before calling it done: the service must report a graph and answer a reviewed public-landmark route.
$port = 3000
if (Test-Path ".env") {
  $m = Select-String -Path ".env" -Pattern "^DEFLOCK_PORT=(\d+)"
  if ($m) { $port = [int]$m.Matches[0].Groups[1].Value }
}
$base = "http://127.0.0.1:$port"
Write-Host "Validating the new graph through the running application..." -ForegroundColor Cyan
$health = $null
for ($i = 0; $i -lt 40; $i++) {
  try {
    $candidate = Invoke-RestMethod -Uri "$base/api/v1/health/data" -TimeoutSec 5
    if ($candidate.router.available) { $health = $candidate; break }
  } catch { }
  Start-Sleep -Seconds 3
}
if (-not $health) { throw "the routing service did not report a graph after the restart; run scripts\rollback_graph.ps1 to restore the previous graph" }
$body = @{ origin = @{ lat = 39.7530; lon = -105.0002 }; destination = @{ lat = 39.7503; lon = -104.9500 } } | ConvertTo-Json -Compress
try {
  $plan = Invoke-RestMethod -Method Post -Uri "$base/api/v1/routes/plan" -ContentType "application/json" -Body $body -TimeoutSec 60
} catch {
  throw "a test route (Union Station to Denver Zoo) failed on the new graph; run scripts\rollback_graph.ps1 to restore the previous graph"
}
Write-Host ("Graph validated: built {0}; test route has {1} maneuvers." -f $health.router.tileset_last_modified, $plan.options[0].maneuvers.Count) -ForegroundColor Green

Write-Host "Refreshing camera road associations on the new graph (cached rows of the old graph are pruned)..." -ForegroundColor Cyan
docker compose --profile setup run --rm associate-cameras
if ($LASTEXITCODE -ne 0) { Write-Warning "association refresh reported failures; routes still assess correctly with live lookups" }
Write-Host ("Done in {0:n0} s. The previous graph is kept in the volume; scripts\rollback_graph.ps1 restores it." -f $sw.Elapsed.TotalSeconds) -ForegroundColor Green
