$ErrorActionPreference = "Stop"
$Api = "http://127.0.0.1:8000"
$Health = Invoke-RestMethod "$Api/health"
if ($Health.status -ne "ok") { throw "Health check failed" }

$Body = @{ agent_id="AGT-SYL-017"; scenario="liquidity_anomaly"; language="banglish" } | ConvertTo-Json
$Accepted = Invoke-RestMethod -Method Post -Uri "$Api/api/v1/analyses" -ContentType "application/json" -Body $Body
for ($i=0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 400
    $Snapshot = Invoke-RestMethod "$Api/api/v1/analyses/$($Accepted.analysis_id)"
    if ($Snapshot.status -eq "completed") { break }
    if ($Snapshot.status -eq "failed") { throw $Snapshot.error }
}
if ($Snapshot.status -ne "completed") { throw "Analysis timeout" }
if (-not $Snapshot.result.alert_id) { throw "Persistent alert missing" }
Write-Host "PHASE 2 VERIFIED: $($Snapshot.result.alert_id)" -ForegroundColor Green
