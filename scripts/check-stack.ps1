# Health check for the running SyncForge dev stack (API + web).
# Usage: powershell -ExecutionPolicy Bypass -File scripts\check-stack.ps1

$ErrorActionPreference = "Continue"

Write-Host "=== API (http://127.0.0.1:8000) ==="
try {
    $h = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 10
    Write-Host ("health      -> " + ($h | ConvertTo-Json -Compress))
} catch {
    Write-Host ("health      -> ERROR " + $_.Exception.Message)
}
foreach ($p in @("/docs", "/openapi.json")) {
    try {
        $r = Invoke-WebRequest -Uri ("http://127.0.0.1:8000" + $p) -UseBasicParsing -TimeoutSec 10
        Write-Host ("{0,-12}-> HTTP {1}" -f $p, $r.StatusCode)
    } catch {
        Write-Host ("{0,-12}-> ERROR {1}" -f $p, $_.Exception.Message)
    }
}

Write-Host "`n=== WEB (http://localhost:3000) ==="
foreach ($p in @("/", "/login", "/dashboard", "/dashboard/meetings", "/dashboard/tasks", "/dashboard/team", "/dashboard/studio", "/dashboard/agent", "/dashboard/memory")) {
    try {
        $r = Invoke-WebRequest -Uri ("http://localhost:3000" + $p) -UseBasicParsing -TimeoutSec 90
        Write-Host ("{0,-22}-> HTTP {1}" -f $p, $r.StatusCode)
    } catch {
        Write-Host ("{0,-22}-> ERROR {1}" -f $p, $_.Exception.Message)
    }
}

Write-Host "`n=== stray DB files in apps/api ==="
Get-ChildItem (Join-Path (Split-Path -Parent $PSScriptRoot) "apps\api") -Filter *.db -ErrorAction SilentlyContinue |
    ForEach-Object { Write-Host ("  " + $_.Name) }
