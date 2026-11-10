# Start, stop or check the local PostgreSQL used for development and tests (no Docker).
#
# Usage, from anywhere in PowerShell:
#   powershell -File backend\scripts\local-db.ps1 start
#   powershell -File backend\scripts\local-db.ps1 stop
#   powershell -File backend\scripts\local-db.ps1 status
#
# Expects the portable PostgreSQL layout from the README:
#   program  %LOCALAPPDATA%\Programs\pgsql-17   (override with $env:MENTORX_PG_HOME)
#   data     %LOCALAPPDATA%\MENTORX\pgdata      (override with $env:MENTORX_PG_DATA)
# A PostgreSQL installed with the official installer runs as a Windows service instead and
# doesn't need this script.

param([ValidateSet("start", "stop", "status")][string]$Action = "status")

$pgHome = if ($env:MENTORX_PG_HOME) { $env:MENTORX_PG_HOME } else { "$env:LOCALAPPDATA\Programs\pgsql-17" }
$data = if ($env:MENTORX_PG_DATA) { $env:MENTORX_PG_DATA } else { "$env:LOCALAPPDATA\MENTORX\pgdata" }
$pgCtl = Join-Path $pgHome "bin\pg_ctl.exe"

if (-not (Test-Path $pgCtl)) {
    Write-Output "PostgreSQL not found at $pgHome. See README, 'Local setup'."
    exit 1
}
if (-not (Test-Path (Join-Path $data "PG_VERSION"))) {
    Write-Output "No database folder at $data. See README, 'Local setup' (initdb step)."
    exit 1
}

switch ($Action) {
    "start" { & $pgCtl -D $data -l (Join-Path $data "server.log") -w start }
    "stop" { & $pgCtl -D $data -m fast stop }
    "status" { & $pgCtl -D $data status }
}
