# Start the SyncForge web app (Next.js dev server) in the background with logging.
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\start-web.ps1 [-Clean]
#
# -Clean wipes .next first. Use it if the dev server shows errors like
# "TypeError: __webpack_modules__[moduleId] is not a function", which happens
# when a production build has overwritten the dev cache.

param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$webDir = Join-Path $root "apps\web"
$logFile = Join-Path $webDir "web.dev.log"
$port = 3000

# Stop any previous instance listening on the port
$existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    foreach ($conn in $existing) {
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
}

if ($Clean) {
    $nextDir = Join-Path $webDir ".next"
    if (Test-Path $nextDir) {
        Write-Host "Removing stale .next cache..."
        Remove-Item -Recurse -Force $nextDir -ErrorAction SilentlyContinue
    }
}

Write-Host "Starting SyncForge web on http://localhost:$port ..."
Start-Process -WindowStyle Hidden -FilePath "cmd.exe" `
    -ArgumentList "/c", "cd /d `"$webDir`" && npx next dev --port $port > `"$logFile`" 2>&1"

$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 1000
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:$port" -UseBasicParsing -TimeoutSec 3
        Write-Host ("Web is up: HTTP " + $resp.StatusCode)
        $ok = $true
        break
    } catch {
        # not ready yet
    }
}

if (-not $ok) {
    Write-Host "Web did not become ready. Last log lines:"
    if (Test-Path $logFile) { Get-Content $logFile -Tail 40 }
    exit 1
}
