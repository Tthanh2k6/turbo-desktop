# Manual smoke test with the REAL agent (spends a little of your Claude quota, uses the Haiku model).
# Starts a throw-away hub (own data folder in %TEMP%\turbo-field, port 8761), pairs a simulated phone,
# runs "compute (12.5 + 7) * 3 in Calculator" through claude headless + desktop-mcp, prints every event.
# Your real hub data is never touched. Usage:  powershell -File hub\scripts\smoke_real.ps1 [calc|deny|stop|restart|orphan|all]
param([string]$Scenario = "calc")
$hub = Split-Path $PSScriptRoot -Parent
$py = Join-Path $hub ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Error "Create the venv first: python -m venv hub\.venv; hub\.venv\Scripts\pip install -r hub\requirements.txt"; exit 1 }
$env:PYTHONIOENCODING = "utf-8"
& $py (Join-Path $PSScriptRoot "field_run.py") $Scenario
Write-Host "Log: $env:TEMP\turbo-field\field_run.log"
