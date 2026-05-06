param(
  [string]$Server = "root@your-server-ip",
  [string]$ProjectDir = "D:\Projects\multi-agents",
  [string]$Archive = "D:\Projects\multi-agents-src.tar.gz",
  [string]$RemoteArchive = "/opt/multi-agents-src.tar.gz",
  [string]$RemoteDeployScript = "/opt/deploy-multi-agents.sh"
)

Write-Host "==> Packing project..."
Set-Location $ProjectDir

if (Test-Path $Archive) {
    Remove-Item $Archive -Force
}

tar `
  --exclude=.git `
  --exclude=backend/.venv `
  --exclude=backend/.env `
  --exclude=frontend/node_modules `
  --exclude=frontend/dist `
  -czf $Archive .

Write-Host "==> Uploading to server..."
scp $Archive "${Server}:$RemoteArchive"

Write-Host "==> Running server deploy script..."
ssh $Server "bash $RemoteDeployScript"

Write-Host "==> Done."
