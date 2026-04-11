param(
  [switch]$Lan
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root 'backend'
$frontendDir = Join-Path $root 'frontend'
$backendPort = 8001

$backendCmd = if ($Lan) {
  "Set-Location '$backendDir'; .\\start.ps1 -Lan -Port $backendPort"
} else {
  "Set-Location '$backendDir'; .\\start.ps1 -Port $backendPort"
}

$frontendCmd = if ($Lan) {
  "Set-Location '$frontendDir'; `$env:VITE_BACKEND_PORT='$backendPort'; npm run dev:lan"
} else {
  "Set-Location '$frontendDir'; `$env:VITE_BACKEND_PORT='$backendPort'; npm run dev"
}

Write-Host "Starting backend and frontend..." -ForegroundColor Green
Write-Host ("Mode: " + ($(if ($Lan) { 'LAN' } else { 'LOCAL' }))) -ForegroundColor Yellow

Start-Process powershell -ArgumentList '-NoExit', '-Command', $backendCmd | Out-Null
Start-Process powershell -ArgumentList '-NoExit', '-Command', $frontendCmd | Out-Null

if ($Lan) {
  Write-Host "LAN mode enabled." -ForegroundColor Cyan
  Write-Host "Use your host IP to access frontend: http://<HOST_IP>:5173" -ForegroundColor Cyan
  Write-Host "Backend API docs: http://<HOST_IP>:$backendPort/docs" -ForegroundColor Cyan
} else {
  Write-Host "Local mode enabled." -ForegroundColor Cyan
  Write-Host "Frontend: http://127.0.0.1:5173" -ForegroundColor Cyan
  Write-Host "Backend API docs: http://127.0.0.1:$backendPort/docs" -ForegroundColor Cyan
}
