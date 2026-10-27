# Cognix AI - One Command Demo
# Starts API and Web servers, waits for them, and opens browser
# Run from repo root: powershell -ExecutionPolicy Bypass -File scripts\demo.ps1

param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Continue"

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Cognix AI - Demo Mode" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $repoRoot -or -not (Test-Path (Join-Path $repoRoot "package.json"))) {
    $repoRoot = (Get-Location).Path
}

Set-Location $repoRoot

# Check if setup needed
if (-not (Test-Path "apps\api\venv\Scripts\python.exe")) {
    Write-Host "Python venv not found. Running setup first..." -ForegroundColor Yellow
    & powershell -ExecutionPolicy Bypass -File "scripts\setup-dev.ps1"
    Write-Host ""
}

if (-not (Test-Path "node_modules")) {
    Write-Host "Node modules not found. Running npm ci..." -ForegroundColor Yellow
    npm ci
    Write-Host ""
}

Write-Host "[1/4] Starting API server (port 8000)..." -ForegroundColor Yellow
$apiJob = Start-Job -ScriptBlock {
    param($root)
    Set-Location (Join-Path $root "apps\api")
    & ".\venv\Scripts\python.exe" -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
} -ArgumentList $repoRoot

Start-Sleep -Seconds 3

Write-Host "[2/4] Starting Web server (port 3000)..." -ForegroundColor Yellow
$webJob = Start-Job -ScriptBlock {
    param($root)
    Set-Location (Join-Path $root "apps\web")
    node scripts/copy-monaco.mjs
    npx next dev --port 3000
} -ArgumentList $repoRoot

Start-Sleep -Seconds 8

Write-Host "[3/4] Waiting for servers to be ready..." -ForegroundColor Yellow
$maxWait = 30
$apiReady = $false
$webReady = $false

for ($i = 0; $i -lt $maxWait; $i++) {
    try {
        $apiResp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
        if ($apiResp.StatusCode -eq 200) { $apiReady = $true }
    } catch {}
    try {
        $webResp = Invoke-WebRequest -Uri "http://localhost:3000" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
        if ($webResp.StatusCode -eq 200) { $webReady = $true }
    } catch {}
    if ($apiReady -and $webReady) { break }
    Start-Sleep -Seconds 2
    Write-Host "  Waiting... ($($i+1)/$maxWait)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Green
Write-Host "  Servers Status" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
Write-Host "  API (FastAPI):  http://127.0.0.1:8000  $(if($apiReady){'[READY]'}else{'[STARTING]'})" -ForegroundColor $(if($apiReady){'Green'}else{'Yellow'})
Write-Host "  Docs (Swagger): http://127.0.0.1:8000/docs" -ForegroundColor White
Write-Host "  Web (Next.js):  http://localhost:3000   $(if($webReady){'[READY]'}else{'[STARTING]'})" -ForegroundColor $(if($webReady){'Green'}else{'Yellow'})
Write-Host "======================================" -ForegroundColor Green
Write-Host ""

if (-not $NoBrowser) {
    Write-Host "[4/4] Opening browser..." -ForegroundColor Yellow
    Start-Sleep -Seconds 2
    Start-Process "http://localhost:3000"
    Write-Host "  Browser opened to http://localhost:3000" -ForegroundColor Green
}

Write-Host ""
Write-Host "Demo is running! Press Ctrl+C to stop all servers." -ForegroundColor Cyan
Write-Host ""
Write-Host "Quick Demo Flow:" -ForegroundColor Yellow
Write-Host "  1. Register/Login at localhost:3000" -ForegroundColor White
Write-Host "  2. Upload a meeting (or use demo data)" -ForegroundColor White
Write-Host "  3. Check Kanban board for auto-generated tasks" -ForegroundColor White
Write-Host "  4. Go to Dev Studio -> Create sample project" -ForegroundColor White
Write-Host "  5. Try Meeting->Code agent and Ship it!" -ForegroundColor White
Write-Host ""

# Keep running and show logs
try {
    while ($true) {
        Start-Sleep -Seconds 30
    }
} finally {
    Write-Host "`nStopping servers..." -ForegroundColor Yellow
    Stop-Job $apiJob -ErrorAction SilentlyContinue
    Stop-Job $webJob -ErrorAction SilentlyContinue
    Remove-Job $apiJob -ErrorAction SilentlyContinue
    Remove-Job $webJob -ErrorAction SilentlyContinue
    Write-Host "Servers stopped." -ForegroundColor Green
}
