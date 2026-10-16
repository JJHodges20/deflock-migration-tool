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
Write-Host ("Done in {0:n0} s. Check Data Health in the app for the new graph date." -f $sw.Elapsed.TotalSeconds) -ForegroundColor Green
