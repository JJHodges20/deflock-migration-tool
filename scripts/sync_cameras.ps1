<#
.SYNOPSIS
  Operator-triggered camera inventory refresh: one bounded Overpass query for the fixed Denver
  envelope, validated and promoted atomically. The scheduled worker does the same every 6 hours
  while the stack runs; this script is for a manual refresh.
#>
[CmdletBinding()]
param([switch]$Force)  # ignore the shared cooldown (operator refreshes are otherwise limited to one per cooldown period)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Running one camera sync (fixed region, never a trip)..." -ForegroundColor Cyan
$syncArgs = @("--once", "--trigger", "manual")
if ($Force) { $syncArgs += "--force" }
docker compose run --rm camera-sync python -m deflockmigration.workers.camera_sync @syncArgs
if ($LASTEXITCODE -ne 0) { throw "camera sync did not publish a new snapshot; the last good snapshot remains active (see the log above)" }
Write-Host "Camera sync finished (a skipped line above means the shared cooldown applied; add -Force to override). Data Health in the app shows the result." -ForegroundColor Green
