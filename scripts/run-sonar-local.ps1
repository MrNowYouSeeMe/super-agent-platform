param(
    [string]$Token = $env:SONAR_TOKEN
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Root = "D:\SUST-CSE-Carnival-2026\super-agent-platform"
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

if ([string]::IsNullOrWhiteSpace($Token)) {
    $SecureToken = Read-Host "Paste SONAR_TOKEN locally" -AsSecureString
    $Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureToken)

    try {
        $Token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer)
    }
}

if ([string]::IsNullOrWhiteSpace($Token)) {
    throw "SONAR_TOKEN is required"
}

Set-Location $Backend
.\.venv\Scripts\python.exe -m pip install pytest-cov
.\.venv\Scripts\python.exe -m pytest -q `
    --cov=app `
    --cov-report=xml:coverage.xml `
    --cov-report=term-missing

Set-Location $Frontend
npm.cmd ci
npm.cmd run build

Set-Location $Root

docker run --rm `
    -e SONAR_HOST_URL="https://sonarcloud.io" `
    -e SONAR_TOKEN="$Token" `
    -v "${Root}:/usr/src" `
    -w /usr/src `
    sonarsource/sonar-scanner-cli:latest `
    -Dsonar.qualitygate.wait=true `
    -Dsonar.qualitygate.timeout=300

if ($LASTEXITCODE -ne 0) {
    throw "SonarQube scan or Quality Gate failed"
}

Write-Host ""
Write-Host "LOCAL SONARQUBE QUALITY GATE PASSED" -ForegroundColor Green