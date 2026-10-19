<#
.SYNOPSIS
  Operator review of quarantined camera snapshots. A quarantined snapshot (empty result or a large
  drop in mapped records) is never published automatically; the last good snapshot stays active
  until an operator accepts or rejects it after corroboration.

.EXAMPLE
  scripts\review_snapshot.ps1 list
  scripts\review_snapshot.ps1 list -All
  scripts\review_snapshot.ps1 accept ovp-denver-20261016T020000Z-abcd1234 -Note "mass retirement corroborated in OSM history"
  scripts\review_snapshot.ps1 reject ovp-denver-20261016T020000Z-abcd1234 -Note "partial upstream response"
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true, Position = 0)][ValidateSet("list", "accept", "reject")][string]$Command,
  [Parameter(Position = 1)][string]$SnapshotId,
  [string]$Note,
  [switch]$All
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$cliArgs = @("deflock-snapshot-review", $Command)
if ($Command -eq "list") {
  if ($All) { $cliArgs += "--all" }
} else {
  if (-not $SnapshotId) { throw "SnapshotId is required for $Command" }
  if (-not $Note) { throw "-Note is required for $Command (explain the corroboration or the rejection)" }
  $cliArgs += @($SnapshotId, "--note", $Note)
}
docker compose run --rm camera-sync @cliArgs
exit $LASTEXITCODE
