$ErrorActionPreference = "Stop"

$Root = "D:\SUST-CSE-Carnival-2026\super-agent-platform"
Set-Location $Root

$EnvMap = @{}
Get-Content .env | ForEach-Object {
    if ($_ -match "^([^#=]+)=(.*)$") {
        $EnvMap[$matches[1].Trim()] = $matches[2].Trim()
    }
}

$ApiPort = if ($EnvMap.BACKEND_HOST_PORT) { $EnvMap.BACKEND_HOST_PORT } else { "8000" }
$JaegerPort = if ($EnvMap.JAEGER_UI_PORT) { $EnvMap.JAEGER_UI_PORT } else { "16686" }
$Api = "http://127.0.0.1:$ApiPort"
$Jaeger = "http://127.0.0.1:$JaegerPort"

$RequestId = "trace-test-$([guid]::NewGuid().ToString('N').Substring(0,16))"
$Body = @{
    agent_id = "AGT-SYL-017"
    scenario = "liquidity_anomaly"
    language = "banglish"
} | ConvertTo-Json

$Create = Invoke-WebRequest `
    -Method Post `
    -Uri "$Api/api/v1/analyses" `
    -Headers @{ "X-Request-ID" = $RequestId } `
    -ContentType "application/json" `
    -Body $Body `
    -UseBasicParsing

$TraceId = $Create.Headers["X-Trace-ID"]
if ([string]::IsNullOrWhiteSpace($TraceId)) {
    throw "X-Trace-ID response header is missing"
}

$Accepted = $Create.Content | ConvertFrom-Json
$Snapshot = $null

for ($i = 0; $i -lt 120; $i++) {
    Start-Sleep -Milliseconds 500
    $Snapshot = Invoke-RestMethod "$Api/api/v1/analyses/$($Accepted.analysis_id)"
    if ($Snapshot.status -eq "completed") { break }
    if ($Snapshot.status -eq "failed") { throw $Snapshot.error }
}

if ($Snapshot.status -ne "completed") {
    throw "Analysis did not complete"
}

$FoundDistributedTrace = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 1
    try {
        $TraceResponse = Invoke-RestMethod "$Jaeger/api/traces/$TraceId"
        foreach ($TraceItem in @($TraceResponse.data)) {
            $Services = @(
                $TraceItem.processes.PSObject.Properties.Value.serviceName |
                    Sort-Object -Unique
            )
            if (
                $Services -contains "superagent-api" -and
                $Services -contains "superagent-worker"
            ) {
                $FoundDistributedTrace = $true
                break
            }
        }
    }
    catch {}
    if ($FoundDistributedTrace) { break }
}

if (-not $FoundDistributedTrace) {
    throw "A shared API-to-worker distributed trace was not found in Jaeger"
}

$Logs = docker compose logs --tail 250 backend worker
if (($Logs -join "`n") -notmatch $TraceId) {
    throw "Trace ID was not correlated into structured logs"
}

Write-Host "OBSERVABILITY VERIFIED" -ForegroundColor Green
Write-Host "Trace ID: $TraceId"
Write-Host "Analysis: $($Accepted.analysis_id)"
Write-Host "Jaeger: $Jaeger/trace/$TraceId"
