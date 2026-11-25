#!/usr/bin/env pwsh
# InspectFlow + SmartExpedit - Local Windows Setup Script

Write-Host "InspectFlow + SmartExpedit Setup" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

# Check Python
$pyVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Python 3.10+ is required. Please install Python and re-run." -ForegroundColor Red
    exit 1
}
Write-Host "Detected $pyVersion" -ForegroundColor Green

# Check Node.js
$nodeVersion = node --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Node.js 18+ is required. Please install Node.js and re-run." -ForegroundColor Red
    exit 1
}
Write-Host "Detected Node.js $nodeVersion" -ForegroundColor Green

# Prepare .env from .env.example if missing
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example (edit GEMINI_API_KEY if using AI extraction)." -ForegroundColor Yellow
} else {
    Write-Host ".env already exists (left unchanged)." -ForegroundColor Green
}

Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "Installing Node.js dependencies..." -ForegroundColor Yellow
npm install
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "Building React production bundle..." -ForegroundColor Yellow
npm run build
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host "Start the server with:" -ForegroundColor Cyan
Write-Host "  python -m uvicorn python_app.api_server:app --host 0.0.0.0 --port 5214" -ForegroundColor White
Write-Host "Then open http://localhost:5214" -ForegroundColor White
