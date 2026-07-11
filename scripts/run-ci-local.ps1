$ErrorActionPreference = "Stop"

$Root = "D:\SUST-CSE-Carnival-2026\super-agent-platform"
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

Set-Location $Backend
.\.venv\Scripts\python.exe -m pip install pytest-cov
.\.venv\Scripts\python.exe -m pytest -q `
    --cov=app `
    --cov-report=xml:coverage.xml `
    --cov-report=term-missing

Set-Location $Frontend
npm.cmd install --global npm@11.6.4
npm.cmd ci

npm.cmd run test:coverage
npm.cmd run build
npm.cmd audit --audit-level=high

Set-Location $Root
docker compose config --quiet
docker compose build backend worker frontend

Write-Host ""
Write-Host "LOCAL CI PASSED" -ForegroundColor Green