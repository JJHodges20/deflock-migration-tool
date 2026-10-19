<#
.SYNOPSIS
  Precompute nearest-road candidates for every in-envelope camera record of the active snapshot on the
  current routing-graph version (the association cache). Route assessments fall back to live engine
  lookups for records that are not cached yet, so this is an optimisation and a refresh step after a
  new camera snapshot or a rebuilt graph, not a prerequisite for correctness.
#>
[CmdletBinding()]
param(
    [switch]$Recompute  # drop the current graph's cached rows first (use after the counting method changes)
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$workerArgs = @()
if ($Recompute) { $workerArgs += "--recompute" }
docker compose --profile setup run --rm associate-cameras deflock-associate-cameras @workerArgs
exit $LASTEXITCODE
