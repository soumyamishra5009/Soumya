# Cognix AI - Dev Setup Script
# Installs dependencies for fresh clone (npm + Python venv + requirements)
# Run from repo root: powershell -ExecutionPolicy Bypass -File scripts\setup-dev.ps1

$ErrorActionPreference = "Stop"

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Cognix AI - Development Setup" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Node.js
Write-Host "[1/5] Checking Node.js..." -ForegroundColor Yellow
try {
    $nodeVersion = node --version
    $npmVersion = npm --version
    Write-Host "  Node: $nodeVersion, npm: $npmVersion" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Node.js not found. Install Node.js 20+ from https://nodejs.org/" -ForegroundColor Red
    exit 1
}

# 2. Check Python
Write-Host "[2/5] Checking Python..." -ForegroundColor Yellow
try {
    $pyVersion = python --version 2>&1
    Write-Host "  Python: $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Python not found. Install Python 3.11+ from https://python.org/" -ForegroundColor Red
    exit 1
}

# 3. Install Node dependencies
Write-Host "[3/5] Installing Node dependencies (npm ci)..." -ForegroundColor Yellow
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $repoRoot) { $repoRoot = (Get-Location).Path }
Set-Location $repoRoot
npm ci
Write-Host "  Node dependencies installed" -ForegroundColor Green

# 4. Setup Python venv and install dependencies
Write-Host "[4/5] Setting up Python environment (apps/api)..." -ForegroundColor Yellow
$apiPath = Join-Path $repoRoot "apps\api"
Set-Location $apiPath
if (-not (Test-Path "venv")) {
    Write-Host "  Creating virtual environment..." -ForegroundColor Cyan
    python -m venv venv
}
Write-Host "  Upgrading pip..." -ForegroundColor Cyan
.\venv\Scripts\python.exe -m pip install --upgrade pip --quiet
Write-Host "  Installing API dependencies (requirements-dev.txt)..." -ForegroundColor Cyan
.\venv\Scripts\pip.exe install -r requirements-dev.txt
Write-Host "  Python environment ready" -ForegroundColor Green

# 5. Copy .env if missing
Write-Host "[5/5] Checking environment files..." -ForegroundColor Yellow
Set-Location $repoRoot
if (-not (Test-Path "apps\api\.env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" "apps\api\.env"
    Write-Host "  Created apps/api/.env from .env.example" -ForegroundColor Green
} elseif (Test-Path "apps\api\.env") {
    Write-Host "  apps/api/.env already exists" -ForegroundColor Green
}
if (-not (Test-Path "apps\web\.env.local") -and (Test-Path "apps\web\.env.example")) {
    Copy-Item "apps\web\.env.example" "apps\web\.env.local"
    Write-Host "  Created apps/web/.env.local from .env.example" -ForegroundColor Green
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Green
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Edit apps/api/.env with your API keys (optional)" -ForegroundColor White
Write-Host "     - GEMINI_API_KEY for real AI (free at aistudio.google.com/apikey)" -ForegroundColor Gray
Write-Host "     - Works offline without keys using extractive fallback" -ForegroundColor Gray
Write-Host "  2. Run: npm run demo  (starts API + Web, opens browser)" -ForegroundColor White
Write-Host "     or:  npm run dev   (starts both services)" -ForegroundColor White
Write-Host ""
