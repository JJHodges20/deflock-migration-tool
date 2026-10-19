<#
.SYNOPSIS
  Put the previous routing graph back. scripts\import_region.ps1 keeps the graph it replaces as the
  last-good graph inside the Docker volume; this script swaps it back and restarts the routing service.
  Nothing is downloaded or rebuilt, and the database is untouched.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Rolling the routing graph back to the last-good build..." -ForegroundColor Cyan
docker compose --profile setup run --rm graph-rollback
if ($LASTEXITCODE -ne 0) { throw "no previous graph to roll back to (see the message above); the active graph is unchanged" }

Write-Host "Restarting the routing service to load it..." -ForegroundColor Cyan
docker compose restart valhalla | Out-Null
Write-Host "Refreshing camera road associations for the restored graph version..." -ForegroundColor Cyan
docker compose --profile setup run --rm associate-cameras
if ($LASTEXITCODE -ne 0) { Write-Warning "association refresh reported failures; routes still assess correctly with live lookups" }
Write-Host "Done. Check Data Health in the app: the graph build date should now be the restored one. Running this script again swaps the graphs back." -ForegroundColor Green
