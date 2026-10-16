# Start the full SyncForge stack (API + web) with one command.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\start-all.ps1
#
#   powershell -ExecutionPolicy Bypass -File scripts\start-all.ps1          # start both
#   powershell -ExecutionPolicy Bypass -File scripts\start-all.ps1 -Stop    # stop both

param(
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$apiDir = Join-Path $root "apps\api"
$webDir = Join-Path $root "apps\web"
$python = Join-Path $apiDir "venv\Scripts\python.exe"

$apiLog = Join-Path $apiDir "api.dev.log"
$webLog = Join-Path $webDir "web.dev.log"

function Stop-Port([int]$port) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conns) {
        foreach ($c in $conns) {
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        }
        Write-Host "Stopped port $port"
    }
}

if ($Stop) {
    Stop-Port 8000
    Stop-Port 3000
    Write-Host "SyncForge stack stopped."
    exit 0
}

if (-not (Test-Path $python)) {
    Write-Error "venv not found at $python. Run: python -m venv venv  (inside apps\api)"
    exit 1
}

# Stop anything already running
Stop-Port 8000
Stop-Port 3000
Start-Sleep -Seconds 1

Write-Host "Starting SyncForge API on http://127.0.0.1:8000 ..."
Start-Process -WindowStyle Hidden -FilePath "cmd.exe" `
    -ArgumentList "/c", "cd /d `"$apiDir`" && `"$python`" -m uvicorn main:app --host 127.0.0.1 --port 8000 > `"$apiLog`" 2>&1"

Write-Host "Starting SyncForge web on http://localhost:3000 ..."
Start-Process -WindowStyle Hidden -FilePath "cmd.exe" `
    -ArgumentList "/c", "cd /d `"$webDir`" && npm run dev > `"$webLog`" 2>&1"

# Wait for both to be ready
$apiUp = $false
$webUp = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 800
    if (-not $apiUp) {
        try {
            $r = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 3
            Write-Host ("API is up: " + ($r | ConvertTo-Json -Compress))
            $apiUp = $true
        } catch { }
    }
    if (-not $webUp) {
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 5
            Write-Host ("Web is up: HTTP " + $r.StatusCode)
            $webUp = $true
        } catch { }
    }
    if ($apiUp -and $webUp) { break }
}

if ($apiUp -and $webUp) {
    Write-Host ""
    Write-Host "=== SyncForge is running ==="
    Write-Host "  Web:  http://localhost:3000"
    Write-Host "  API:  http://127.0.0.1:8000/docs"
    Write-Host "  Stop: powershell -ExecutionPolicy Bypass -File scripts\start-all.ps1 -Stop"
} else {
    Write-Host ""
    Write-Host "Something did not become ready. Check logs:"
    Write-Host "  API: $apiLog"
    Write-Host "  Web: $webLog"
    exit 1
}
