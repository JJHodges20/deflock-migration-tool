<#
.SYNOPSIS
  Operator-triggered camera inventory refresh: one bounded Overpass query for the fixed Denver
  envelope, validated and promoted atomically. The scheduled worker does the same every 6 hours
  while the stack runs; this script is for a manual refresh.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Running one camera sync (fixed region, never a trip)..." -ForegroundColor Cyan
docker compose run --rm camera-sync python -m deflockmigration.workers.camera_sync --once --trigger manual
if ($LASTEXITCODE -ne 0) { throw "camera sync did not publish a new snapshot; the last good snapshot remains active (see the log above)" }
Write-Host "Camera sync finished. Data Health in the app shows the new snapshot." -ForegroundColor Green
