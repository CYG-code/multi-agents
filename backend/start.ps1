param(
  [switch]$Lan,
  [int]$Port = 8000,
  [switch]$Reload
)

Set-Location $PSScriptRoot

$bindHost = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
Write-Host "[backend] Starting on ${bindHost}:$Port" -ForegroundColor Cyan

$args = @('-m', 'uvicorn', 'app.main:app', '--host', $bindHost, '--port', $Port)
if ($Reload) {
  $args += '--reload'
}

& .\.venv\Scripts\python.exe @args
