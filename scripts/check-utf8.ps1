param(
  [switch]$FailOnBom,
  [switch]$FixBom
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$extensions = @(
  '.js', '.mjs', '.cjs', '.ts', '.tsx', '.vue',
  '.json', '.css', '.html', '.md', '.yml', '.yaml',
  '.py', '.ps1', '.sh', '.ini', '.toml'
)

$utf8Strict = [System.Text.UTF8Encoding]::new($false, $true)
$failures = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$fixed = New-Object System.Collections.Generic.List[string]

$raw = git ls-files -z
if (-not $raw) {
  Write-Host "No tracked files found."
  exit 0
}

$files = ($raw -split "`0") | Where-Object { $_ -ne '' }

foreach ($relative in $files) {
  $fullPath = Join-Path $root $relative
  if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
    continue
  }

  $ext = [System.IO.Path]::GetExtension($fullPath).ToLowerInvariant()
  if ($extensions -notcontains $ext) {
    continue
  }

  try {
    $bytes = [System.IO.File]::ReadAllBytes($fullPath)
  } catch {
    $failures.Add("$relative : cannot read file ($($_.Exception.Message))")
    continue
  }

  if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) {
    $failures.Add("$relative : UTF-16 LE BOM detected")
    continue
  }
  if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF) {
    $failures.Add("$relative : UTF-16 BE BOM detected")
    continue
  }
  if ($bytes.Length -ge 4 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE -and $bytes[2] -eq 0x00 -and $bytes[3] -eq 0x00) {
    $failures.Add("$relative : UTF-32 LE BOM detected")
    continue
  }
  if ($bytes.Length -ge 4 -and $bytes[0] -eq 0x00 -and $bytes[1] -eq 0x00 -and $bytes[2] -eq 0xFE -and $bytes[3] -eq 0xFF) {
    $failures.Add("$relative : UTF-32 BE BOM detected")
    continue
  }

  if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    if ($FixBom) {
      $newBytes = New-Object byte[] ($bytes.Length - 3)
      [Array]::Copy($bytes, 3, $newBytes, 0, $bytes.Length - 3)
      [System.IO.File]::WriteAllBytes($fullPath, $newBytes)
      $bytes = $newBytes
      $fixed.Add("$relative : UTF-8 BOM removed")
    } else {
      $message = "$relative : UTF-8 BOM detected"
      if ($FailOnBom) {
        $failures.Add($message)
      } else {
        $warnings.Add($message)
      }
    }
  }

  try {
    [void]$utf8Strict.GetString($bytes)
  } catch {
    $failures.Add("$relative : invalid UTF-8 byte sequence")
  }
}

if ($warnings.Count -gt 0) {
  Write-Host "Warnings:"
  foreach ($warning in $warnings) {
    Write-Host "  - $warning"
  }
}

if ($fixed.Count -gt 0) {
  Write-Host "Fixed:"
  foreach ($item in $fixed) {
    Write-Host "  - $item"
  }
}

if ($failures.Count -gt 0) {
  Write-Host "Encoding check failed:" -ForegroundColor Red
  foreach ($failure in $failures) {
    Write-Host "  - $failure"
  }
  exit 1
}

Write-Host "UTF-8 check passed for tracked text files." -ForegroundColor Green
