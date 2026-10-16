<#
.SYNOPSIS
  Verifies the running DeFlockMigration stack: service readiness, data health, one real routing
  request through edge -> api -> valhalla, the basemap range support, and (optionally) that a
  restart keeps the data.

.PARAMETER CheckRestart
  Restart the long-running services and verify the snapshot id and graph build date are unchanged.
#>
[CmdletBinding()]
param(
  [switch]$CheckRestart,
  [int]$Port = 0,
  [int]$TimeoutSeconds = 240
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if ($Port -eq 0) {
  # Default to the port configured in .env (DEFLOCK_PORT), falling back to 3000.
  $Port = 3000
  if (Test-Path ".env") {
    $match = Select-String -Path ".env" -Pattern '^\s*DEFLOCK_PORT\s*=\s*(\d+)' | Select-Object -First 1
    if ($match) { $Port = [int]$match.Matches[0].Groups[1].Value }
  }
}
$base = "http://127.0.0.1:$Port"
$failures = New-Object System.Collections.ArrayList

function Report {
  param([bool]$Ok, [string]$Text)
  if ($Ok) { Write-Host ("  [ok]   " + $Text) -ForegroundColor Green }
  else { Write-Host ("  [FAIL] " + $Text) -ForegroundColor Red; [void]$failures.Add($Text) }
}

function Wait-Healthy {
  param([string[]]$Services, [int]$Timeout)
  $deadline = (Get-Date).AddSeconds($Timeout)
  foreach ($service in $Services) {
    while ($true) {
      $id = (docker compose ps -q $service 2>$null | Select-Object -First 1)
      $status = "missing"
      if ($id) {
        $health = docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $id 2>$null
        if ($health) { $status = $health.Trim() }
      }
      if ($status -eq "healthy" -or $status -eq "running") { Report $true ("service " + $service + " is " + $status); break }
      if ((Get-Date) -gt $deadline) { Report $false ("service " + $service + " is " + $status + " after " + $Timeout + " s"); break }
      Start-Sleep -Seconds 3
    }
  }
}

Write-Host "Smoke test against $base" -ForegroundColor Cyan
Wait-Healthy -Services @("db", "valhalla", "api", "web", "edge", "camera-sync") -Timeout $TimeoutSeconds

try { $h = Invoke-WebRequest -UseBasicParsing -Uri "$base/healthz" -TimeoutSec 10; Report ($h.StatusCode -eq 200) "edge /healthz" } catch { Report $false ("edge /healthz: " + $_.Exception.Message) }
try { $live = Invoke-RestMethod -Uri "$base/api/v1/health/live" -TimeoutSec 10; Report ($live.status -eq "ok") ("api live (version " + $live.version + ")") } catch { Report $false ("api live: " + $_.Exception.Message) }

$snapshotBefore = $null; $graphBefore = $null
try {
  $data = Invoke-RestMethod -Uri "$base/api/v1/health/data" -TimeoutSec 20
  Report ($data.router.available -eq $true) ("routing graph available, built " + $data.router.tileset_last_modified)
  Report ($data.database.available -eq $true) "database reachable"
  if ($data.snapshot) {
    $snapshotBefore = $data.snapshot.snapshot_id
    Report $true ("camera snapshot " + $snapshotBefore + " with " + $data.snapshot.alpr_count + " mapped ALPR records (source " + $data.snapshot.timestamp_osm_base + ")")
  } else { Report $false "no camera snapshot published yet (run camera-sync-once)" }
  $graphBefore = $data.router.tileset_last_modified
  if ($data.geocoder.configured) { Write-Host ("  [info] geocoder " + $(if ($data.geocoder.available) { "available" } else { "configured, still importing or unavailable" })) }
} catch { Report $false ("api data health: " + $_.Exception.Message) }

try {
  $body = @{ origin = @{ lat = 39.7530; lon = -105.0002 }; destination = @{ lat = 39.7503; lon = -104.9500 } } | ConvertTo-Json -Compress
  $plan = Invoke-RestMethod -Method Post -Uri "$base/api/v1/routes/plan" -ContentType "application/json" -Body $body -TimeoutSec 30
  $opt = $plan.options[0]
  $ok = ($plan.options.Count -ge 1) -and ($opt.maneuvers.Count -gt 2) -and ($opt.assessment_coverage_status -eq "not_assessed") -and ($null -eq $opt.matched_camera_record_count)
  Report $ok ("routing request through edge -> api -> valhalla: " + $opt.maneuvers.Count + " maneuvers, " + [math]::Round($opt.estimated_duration_seconds / 60) + " min, " + [math]::Round($opt.length_meters / 1000, 1) + " km (Union Station to Denver Zoo)")
} catch { Report $false ("routing request: " + $_.Exception.Message) }

try {
  $req = [System.Net.HttpWebRequest]::Create("$base/basemap/denver.pmtiles")
  $req.Method = "GET"; $req.AddRange(0, 1023); $req.Timeout = 10000
  $resp = $req.GetResponse()
  # A 206 with a Content-Range header proves byte-range support (nginx only adds Accept-Ranges to full 200 responses).
  $contentRange = [string]$resp.Headers["Content-Range"]
  $ok = ([int]$resp.StatusCode -eq 206) -and ($contentRange -like "bytes 0-1023/*")
  $resp.Close()
  Report $ok ("basemap archive served with HTTP range support (" + $contentRange + ")")
} catch { Report $false ("basemap: " + $_.Exception.Message) }

try {
  $font = Invoke-WebRequest -UseBasicParsing -Uri "$base/basemap/fonts/Noto%20Sans%20Regular/0-255.pbf" -TimeoutSec 10
  Report ($font.StatusCode -eq 200) "basemap fonts self-hosted"
} catch { Report $false ("basemap fonts: " + $_.Exception.Message) }

if ($CheckRestart) {
  Write-Host "Restarting services to verify persistence..." -ForegroundColor Cyan
  docker compose restart db valhalla api web edge camera-sync | Out-Null
  Wait-Healthy -Services @("db", "valhalla", "api", "web", "edge") -Timeout $TimeoutSeconds
  try {
    $after = Invoke-RestMethod -Uri "$base/api/v1/health/data" -TimeoutSec 20
    Report ($after.snapshot.snapshot_id -eq $snapshotBefore) ("camera snapshot survived restart (" + $after.snapshot.snapshot_id + ")")
    Report ($after.router.tileset_last_modified -eq $graphBefore) ("routing graph survived restart (built " + $after.router.tileset_last_modified + ")")
  } catch { Report $false ("post-restart health: " + $_.Exception.Message) }
}

if ($failures.Count -gt 0) {
  Write-Host ("Smoke test FAILED: " + $failures.Count + " problem(s)") -ForegroundColor Red
  exit 1
}
Write-Host "Smoke test passed." -ForegroundColor Green
exit 0
