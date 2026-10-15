# Start the SyncForge API (FastAPI/uvicorn) in the background with logging.
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\start-api.ps1

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$apiDir = Join-Path $root "apps\api"
$python = Join-Path $apiDir "venv\Scripts\python.exe"
$logFile = Join-Path $apiDir "api.dev.log"

if (-not (Test-Path $python)) {
    Write-Error "venv not found at $python. Run: python -m venv venv  (inside apps\api)"
    exit 1
}

# Stop any previous instance listening on 8000
$existing = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    foreach ($conn in $existing) {
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
}

Write-Host "Starting SyncForge API on http://127.0.0.1:8000 ..."
Start-Process -WindowStyle Hidden -FilePath "cmd.exe" `
    -ArgumentList "/c", "cd /d `"$apiDir`" && `"$python`" -m uvicorn main:app --host 127.0.0.1 --port 8000 > `"$logFile`" 2>&1"

# Wait for readiness
$ok = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 700
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 3
        Write-Host ("API is up: " + ($resp | ConvertTo-Json -Compress))
        $ok = $true
        break
    } catch {
        # not ready yet
    }
}

if (-not $ok) {
    Write-Host "API did not become ready. Last log lines:"
    if (Test-Path $logFile) { Get-Content $logFile -Tail 30 }
    exit 1
}
