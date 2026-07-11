$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$Root = "D:\SUST-CSE-Carnival-2026\super-agent-platform"
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$DataDir = Join-Path $Root "data\synthetic"
$ReportDir = Join-Path $Root "artifacts\evaluation"
$StartedAt = Get-Date
$Stamp = $StartedAt.ToString("yyyyMMdd-HHmmss")
$Results = New-Object System.Collections.Generic.List[object]

function Assert-True {
    param(
        [Parameter(Mandatory = $true)][bool]$Condition,
        [Parameter(Mandatory = $true)][string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Test-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )

    $Timer = [System.Diagnostics.Stopwatch]::StartNew()

    try {
        $Detail = & $Action
        $Timer.Stop()

        $Results.Add([pscustomobject]@{
            Test = $Name
            Result = "PASS"
            DurationMs = $Timer.ElapsedMilliseconds
            Detail = if ($null -eq $Detail) { "" } else { [string]$Detail }
        })

        Write-Host ("{0,-48} PASS" -f $Name) -ForegroundColor Green
    }
    catch {
        $Timer.Stop()

        $Results.Add([pscustomobject]@{
            Test = $Name
            Result = "FAIL"
            DurationMs = $Timer.ElapsedMilliseconds
            Detail = $_.Exception.Message
        })

        Write-Host ("{0,-48} FAIL" -f $Name) -ForegroundColor Red
        Write-Host ("  " + $_.Exception.Message) -ForegroundColor DarkRed
    }
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$File,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$Capture,
        [switch]$IgnoreFailure
    )

    $OldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    if ($Capture) {
        $Output = & $File @Arguments 2>&1
    }
    else {
        & $File @Arguments
        $Output = $null
    }

    $ExitCode = $LASTEXITCODE
    $ErrorActionPreference = $OldPreference

    if (-not $IgnoreFailure -and $ExitCode -ne 0) {
        throw "$File $($Arguments -join ' ') failed with exit code $ExitCode"
    }

    if ($Capture) {
        return ,@($Output)
    }
}

function Read-EnvMap {
    param([string]$Path)

    $Map = @{}

    if (Test-Path $Path) {
        foreach ($Line in Get-Content $Path) {
            if (
                -not [string]::IsNullOrWhiteSpace($Line) -and
                -not $Line.TrimStart().StartsWith("#") -and
                $Line.Contains("=")
            ) {
                $Pair = $Line -split "=", 2
                $Map[$Pair[0].Trim()] = $Pair[1].Trim()
            }
        }
    }

    return $Map
}

function Wait-Health {
    param([string]$BaseUrl)

    for ($Attempt = 0; $Attempt -lt 90; $Attempt++) {
        try {
            $Health = Invoke-RestMethod `
                -Uri "$BaseUrl/health?nonce=$([guid]::NewGuid().ToString('N'))" `
                -Headers @{ "Cache-Control" = "no-cache" } `
                -TimeoutSec 4

            if (
                $Health.status -eq "ok" -and
                $Health.version -eq "0.3.0" -and
                $Health.dependencies.postgres -eq "ok" -and
                $Health.dependencies.redis -eq "ok"
            ) {
                return $Health
            }
        }
        catch {}

        Start-Sleep -Seconds 1
    }

    throw "Phase 3 API did not become healthy"
}

Write-Host "SUPERAGENT SENTINEL - COMPLETE PHASE 3 TEST SUITE" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $Root)) {
    throw "Project root not found: $Root"
}

Set-Location $Root

$Env = Read-EnvMap (Join-Path $Root ".env")
$ApiPort = if ($Env.ContainsKey("BACKEND_HOST_PORT")) { [int]$Env["BACKEND_HOST_PORT"] } else { 8000 }
$FrontendPort = if ($Env.ContainsKey("FRONTEND_HOST_PORT")) { [int]$Env["FRONTEND_HOST_PORT"] } else { 8080 }

$ApiBase = "http://127.0.0.1:$ApiPort"
$FrontendBase = "http://127.0.0.1:$FrontendPort"

Test-Step "Phase 3 source structure" {
    $RequiredFiles = @(
        "backend\app\evaluation\synthetic.py",
        "backend\app\evaluation\metrics.py",
        "backend\app\evaluation\service.py",
        "backend\app\evaluation\router.py",
        "backend\app\evaluation\contracts.py",
        "backend\app\evaluation\cli.py",
        "backend\tests\test_evaluation.py",
        "data\synthetic\agent_hourly.csv",
        "data\synthetic\provider_hourly.csv",
        "data\synthetic\manifest.json",
        "artifacts\evaluation\latest_metrics.json",
        "artifacts\evaluation\latest_report.md"
    )

    foreach ($RelativePath in $RequiredFiles) {
        Assert-True `
            (Test-Path (Join-Path $Root $RelativePath)) `
            "Missing Phase 3 file: $RelativePath"
    }
}

Test-Step "Docker Phase 3 services running" {
    foreach ($Service in @("postgres", "redis", "backend", "worker", "frontend")) {
        $ContainerId = (
            Invoke-Native `
                -File "docker" `
                -Arguments @("compose", "ps", "-q", $Service) `
                -Capture
        ) -join ""

        $ContainerId = $ContainerId.Trim()
        Assert-True (-not [string]::IsNullOrWhiteSpace($ContainerId)) "No container for $Service"

        $State = (
            Invoke-Native `
                -File "docker" `
                -Arguments @("inspect", "-f", "{{.State.Status}}", $ContainerId) `
                -Capture
        ) -join ""

        Assert-True ($State.Trim() -eq "running") "$Service is not running"
    }
}

Test-Step "Phase 3 health and dependency contract" {
    $Health = Wait-Health $ApiBase
    Assert-True ($Health.version -eq "0.3.0") "API version is not 0.3.0"
    Assert-True ($Health.dependencies.postgres -eq "ok") "PostgreSQL health failed"
    Assert-True ($Health.dependencies.redis -eq "ok") "Redis health failed"
}

Test-Step "Evaluation API contract" {
    $Dataset = Invoke-RestMethod `
        -Uri "$ApiBase/api/v1/evaluation/dataset" `
        -TimeoutSec 15

    $Report = Invoke-RestMethod `
        -Uri "$ApiBase/api/v1/evaluation/report" `
        -TimeoutSec 15

    Assert-True ($Dataset.dataset_version -eq "phase3-synthetic-v1") "Wrong dataset version"
    Assert-True ($Dataset.seed -eq 20260711) "Wrong reproducibility seed"
    Assert-True ($Dataset.agents -eq 18) "Expected 18 agents"
    Assert-True (@($Dataset.providers).Count -eq 3) "Expected 3 providers"
    Assert-True ($Dataset.agent_rows -eq 9072) "Unexpected agent row count"
    Assert-True ($Dataset.provider_rows -eq 27216) "Unexpected provider row count"
    Assert-True ($Dataset.shortage_positive_rows -gt 0) "No shortage positives"
    Assert-True ($Dataset.anomaly_positive_rows -gt 0) "No anomaly positives"
    Assert-True ($Dataset.data_quality_positive_rows -gt 0) "No data quality positives"
    Assert-True (@($Dataset.assumptions).Count -gt 0) "Dataset assumptions missing"
    Assert-True (@($Dataset.limitations).Count -gt 0) "Dataset limitations missing"

    Assert-True ($Report.report_version -eq "phase3-evaluation-v1") "Wrong report version"
    Assert-True ($Report.dataset_version -eq $Dataset.dataset_version) "Dataset/report version mismatch"
    Assert-True ($Report.seed -eq $Dataset.seed) "Dataset/report seed mismatch"
    Assert-True ($Report.measured_metrics_count -ge 3) "Too few measured metrics"
    Assert-True (@($Report.forecast_candidates).Count -eq 3) "Expected 3 forecast candidates"

    $LowestMaeCandidate = @($Report.forecast_candidates) |
        Sort-Object mae_bdt |
        Select-Object -First 1

    Assert-True `
        ($Report.champion_forecast_model -eq $LowestMaeCandidate.model) `
        "Champion is not the lowest-MAE forecast candidate"

    Assert-True ($Report.explanation_coverage -eq 1.0) "Explanation coverage below 100%"
    Assert-True ($Report.safe_language_coverage -eq 1.0) "Safe-language coverage below 100%"
}

Test-Step "Dataset file hashes match manifest" {
    $Manifest = Get-Content `
        (Join-Path $DataDir "manifest.json") `
        -Raw |
        ConvertFrom-Json

    foreach ($File in $Manifest.files) {
        $Path = Join-Path $Root $File.path
        Assert-True (Test-Path $Path) "Manifest file missing: $($File.path)"

        $Hash = (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLowerInvariant()

        Assert-True `
            ($Hash -eq $File.sha256.ToLowerInvariant()) `
            "Hash mismatch: $($File.path)"
    }
}

Test-Step "CSV row counts and schema" {
    $AgentRows = Import-Csv (Join-Path $DataDir "agent_hourly.csv")
    $ProviderRows = Import-Csv (Join-Path $DataDir "provider_hourly.csv")

    Assert-True ($AgentRows.Count -eq 9072) "Agent CSV row count mismatch"
    Assert-True ($ProviderRows.Count -eq 27216) "Provider CSV row count mismatch"

    $RequiredAgentColumns = @(
        "timestamp",
        "split",
        "agent_id",
        "area",
        "shared_cash_before_bdt",
        "shared_cash_after_bdt",
        "shared_cash_safe_threshold_bdt",
        "ground_truth_shortage_within_6h"
    )

    foreach ($Column in $RequiredAgentColumns) {
        Assert-True `
            ($AgentRows[0].PSObject.Properties.Name -contains $Column) `
            "Agent CSV column missing: $Column"
    }

    $RequiredProviderColumns = @(
        "timestamp",
        "split",
        "agent_id",
        "provider",
        "cash_in_bdt",
        "cash_out_bdt",
        "provider_emoney_before_bdt",
        "provider_emoney_after_bdt",
        "feed_status",
        "ground_truth_anomaly",
        "ground_truth_data_quality_issue"
    )

    foreach ($Column in $RequiredProviderColumns) {
        Assert-True `
            ($ProviderRows[0].PSObject.Properties.Name -contains $Column) `
            "Provider CSV column missing: $Column"
    }
}

Test-Step "Provider boundary invariants" {
    $ProviderRows = Import-Csv (Join-Path $DataDir "provider_hourly.csv")

    $Providers = @(
        $ProviderRows.provider |
            Sort-Object -Unique
    )

    Assert-True `
        (($Providers -join ",") -eq "bKash,Nagad,Rocket") `
        "Unexpected provider set: $($Providers -join ',')"

    foreach ($Row in $ProviderRows | Select-Object -First 3000) {
        $Expected = [double]$Row.provider_emoney_before_bdt `
            - [double]$Row.cash_in_bdt `
            + [double]$Row.cash_out_bdt `
            + [double]$Row.authorized_topup_bdt

        $Actual = [double]$Row.provider_emoney_after_bdt

        Assert-True `
            ([math]::Abs($Expected - $Actual) -le 10) `
            "Provider balance equation failed for $($Row.agent_id)/$($Row.provider)"
    }
}

Test-Step "Shared cash accounting invariants" {
    $AgentRows = Import-Csv (Join-Path $DataDir "agent_hourly.csv")

    foreach ($Row in $AgentRows | Select-Object -First 3000) {
        $Expected = [double]$Row.shared_cash_before_bdt `
            + [double]$Row.net_cash_change_bdt `
            + [double]$Row.authorized_cash_support_bdt

        $Actual = [double]$Row.shared_cash_after_bdt

        Assert-True `
            ([math]::Abs($Expected - $Actual) -le 10) `
            "Shared cash equation failed for $($Row.agent_id)"
    }
}

Test-Step "Time-ordered split and leakage guard" {
    $AgentRows = Import-Csv (Join-Path $DataDir "agent_hourly.csv")

    foreach ($AgentGroup in ($AgentRows | Group-Object agent_id)) {
        $Rows = @($AgentGroup.Group)

        $TrainMax = (
            $Rows |
                Where-Object { $_.split -eq "train" } |
                ForEach-Object { [datetimeoffset]$_.timestamp } |
                Measure-Object -Maximum
        ).Maximum

        $ValidationMin = (
            $Rows |
                Where-Object { $_.split -eq "validation" } |
                ForEach-Object { [datetimeoffset]$_.timestamp } |
                Measure-Object -Minimum
        ).Minimum

        $ValidationMax = (
            $Rows |
                Where-Object { $_.split -eq "validation" } |
                ForEach-Object { [datetimeoffset]$_.timestamp } |
                Measure-Object -Maximum
        ).Maximum

        $TestMin = (
            $Rows |
                Where-Object { $_.split -eq "test" } |
                ForEach-Object { [datetimeoffset]$_.timestamp } |
                Measure-Object -Minimum
        ).Minimum

        Assert-True ($TrainMax -lt $ValidationMin) "Train/validation leakage for $($AgentGroup.Name)"
        Assert-True ($ValidationMax -lt $TestMin) "Validation/test leakage for $($AgentGroup.Name)"
    }
}

Test-Step "Positive labels exist in evaluation split" {
    $AgentRows = Import-Csv (Join-Path $DataDir "agent_hourly.csv")
    $ProviderRows = Import-Csv (Join-Path $DataDir "provider_hourly.csv")

    $TestShortage = @(
        $AgentRows |
            Where-Object {
                $_.split -eq "test" -and
                $_.ground_truth_shortage_within_6h -eq "1"
            }
    ).Count

    $TestAnomaly = @(
        $ProviderRows |
            Where-Object {
                $_.split -eq "test" -and
                $_.ground_truth_anomaly -eq "1"
            }
    ).Count

    $TestQuality = @(
        $ProviderRows |
            Where-Object {
                $_.split -eq "test" -and
                $_.ground_truth_data_quality_issue -eq "1"
            }
    ).Count

    Assert-True ($TestShortage -gt 0) "No shortage positives in test split"
    Assert-True ($TestAnomaly -gt 0) "No anomaly positives in test split"
    Assert-True ($TestQuality -gt 0) "No data-quality positives in test split"

    "test positives: shortage=$TestShortage anomaly=$TestAnomaly quality=$TestQuality"
}

Test-Step "Forecast metrics consistency" {
    $Report = Get-Content `
        (Join-Path $ReportDir "latest_metrics.json") `
        -Raw |
        ConvertFrom-Json

    $Candidates = @($Report.forecast_candidates)

    foreach ($Candidate in $Candidates) {
        Assert-True ($Candidate.mae_bdt -ge 0) "Negative MAE"
        Assert-True ($Candidate.rmse_bdt -ge $Candidate.mae_bdt) "RMSE below MAE"
        Assert-True ($Candidate.mape_percent -ge 0) "Negative MAPE"
        Assert-True ($Candidate.evaluated_rows -gt 0) "No evaluated forecast rows"
    }

    $Champion = $Candidates |
        Sort-Object mae_bdt |
        Select-Object -First 1

    Assert-True `
        ($Champion.model -eq $Report.champion_forecast_model) `
        "Champion is not the lowest-MAE candidate"

    Assert-True `
        ([double]$Champion.mae_bdt -le 12000) `
        "Champion MAE exceeds the Phase 3 acceptance threshold"

    Assert-True `
        ([double]$Champion.mape_percent -le 15) `
        "Champion MAPE exceeds the Phase 3 acceptance threshold"
}

Test-Step "Classification metric formulas" {
    $Report = Get-Content `
        (Join-Path $ReportDir "latest_metrics.json") `
        -Raw |
        ConvertFrom-Json

    foreach ($Name in @(
        "shortage_detection",
        "anomaly_detection",
        "data_quality_detection"
    )) {
        $Metric = $Report.$Name

        $Precision = if (($Metric.true_positive + $Metric.false_positive) -gt 0) {
            $Metric.true_positive / ($Metric.true_positive + $Metric.false_positive)
        }
        else { 0 }

        $Recall = if (($Metric.true_positive + $Metric.false_negative) -gt 0) {
            $Metric.true_positive / ($Metric.true_positive + $Metric.false_negative)
        }
        else { 0 }

        $F1 = if (($Precision + $Recall) -gt 0) {
            2 * $Precision * $Recall / ($Precision + $Recall)
        }
        else { 0 }

        $Fpr = if (($Metric.false_positive + $Metric.true_negative) -gt 0) {
            $Metric.false_positive / ($Metric.false_positive + $Metric.true_negative)
        }
        else { 0 }

        Assert-True `
            ([math]::Abs($Precision - [double]$Metric.precision) -lt 0.0002) `
            "$Name precision formula mismatch"

        Assert-True `
            ([math]::Abs($Recall - [double]$Metric.recall) -lt 0.0002) `
            "$Name recall formula mismatch"

        Assert-True `
            ([math]::Abs($F1 - [double]$Metric.f1) -lt 0.0002) `
            "$Name F1 formula mismatch"

        Assert-True `
            ([math]::Abs($Fpr - [double]$Metric.false_positive_rate) -lt 0.0002) `
            "$Name FPR formula mismatch"
    }
}

Test-Step "Phase 3 headline metrics threshold" {
    $Report = Invoke-RestMethod `
        -Uri "$ApiBase/api/v1/evaluation/report" `
        -TimeoutSec 15

    $Champion = @($Report.forecast_candidates) |
        Where-Object { $_.model -eq $Report.champion_forecast_model } |
        Select-Object -First 1

    Assert-True ($Champion.mape_percent -le 15) "Forecast MAPE exceeds 15%"
    Assert-True ($Report.shortage_detection.recall -ge 0.70) "Shortage recall below 70%"
    Assert-True ($Report.anomaly_detection.f1 -ge 0.85) "Anomaly F1 below 85%"
    Assert-True ($Report.data_quality_detection.f1 -ge 0.95) "Data-quality F1 below 95%"
    Assert-True ($Report.shortage_detection.mean_lead_time_minutes -gt 0) "Lead time missing"
    Assert-True ($Report.evaluation_runtime_ms -gt 0) "Evaluation runtime missing"

    "MAPE=$($Champion.mape_percent)% shortage_recall=$([math]::Round($Report.shortage_detection.recall*100,2))% anomaly_F1=$([math]::Round($Report.anomaly_detection.f1*100,2))%"
}

Test-Step "Synthetic data reproducibility" {
    $TempRoot = Join-Path $env:TEMP ("superagent-phase3-repro-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $TempRoot -Force | Out-Null

    $PythonCode = @'
from pathlib import Path
import json
import sys

from app.evaluation.synthetic import SyntheticConfig, generate_dataset

root = Path(sys.argv[1])
a = root / "a"
b = root / "b"

config = SyntheticConfig(agents=4, days=8, seed=12345)
ma = generate_dataset(a, config)
mb = generate_dataset(b, config)

assert ma["agent_rows"] == mb["agent_rows"]
assert ma["provider_rows"] == mb["provider_rows"]
assert ma["files"][0]["sha256"] == mb["files"][0]["sha256"]
assert ma["files"][1]["sha256"] == mb["files"][1]["sha256"]

print(json.dumps({
    "agent_rows": ma["agent_rows"],
    "provider_rows": ma["provider_rows"],
    "sha_a": ma["files"][0]["sha256"],
    "sha_b": ma["files"][1]["sha256"]
}))
'@

    $Probe = Join-Path $TempRoot "repro_check.py"
    [System.IO.File]::WriteAllText($Probe, $PythonCode)

    Set-Location $Backend

    $PreviousPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = $Backend

    try {
        $Output = Invoke-Native `
            -File ".\.venv\Scripts\python.exe" `
            -Arguments @($Probe, $TempRoot) `
            -Capture
    }
    finally {
        $env:PYTHONPATH = $PreviousPythonPath
        Set-Location $Root
        Remove-Item $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }

    $Json = ($Output -join "`n") | ConvertFrom-Json

    Assert-True ($Json.agent_rows -gt 0) "Reproducibility test generated no rows"
    Assert-True ($Json.provider_rows -gt 0) "Reproducibility test generated no provider rows"
}

Test-Step "Evaluation report artifacts are readable" {
    $Metrics = Get-Content `
        (Join-Path $ReportDir "latest_metrics.json") `
        -Raw |
        ConvertFrom-Json

    $Markdown = Get-Content `
        (Join-Path $ReportDir "latest_report.md") `
        -Raw

    Assert-True ($Metrics.report_version -eq "phase3-evaluation-v1") "Metrics JSON invalid"
    Assert-True ($Markdown -match "Forecast") "Markdown report lacks forecast section"
    Assert-True ($Markdown -match "Anomaly") "Markdown report lacks anomaly section"
    Assert-True ($Markdown -match "Shortage") "Markdown report lacks shortage section"
    Assert-True ($Markdown -match "Limitations") "Markdown report lacks limitations"
}

Test-Step "Phase 2 API regression" {
    $Dashboard = Invoke-RestMethod `
        -Uri "$ApiBase/api/v1/dashboard" `
        -TimeoutSec 15

    Assert-True ($Dashboard.agent_id -eq "AGT-SYL-017") "Dashboard contract broke"
    Assert-True (@($Dashboard.provider_balances).Count -eq 3) "Provider balances broke"

    $Body = @{
        agent_id = "AGT-SYL-017"
        scenario = "normal_day"
        language = "en"
    } | ConvertTo-Json

    $Accepted = Invoke-RestMethod `
        -Method Post `
        -Uri "$ApiBase/api/v1/analyses" `
        -ContentType "application/json" `
        -Body $Body `
        -TimeoutSec 15

    $Snapshot = $null

    for ($Attempt = 0; $Attempt -lt 120; $Attempt++) {
        Start-Sleep -Milliseconds 400

        $Snapshot = Invoke-RestMethod `
            -Uri "$ApiBase/api/v1/analyses/$($Accepted.analysis_id)" `
            -TimeoutSec 15

        if ($Snapshot.status -eq "completed") {
            break
        }

        if ($Snapshot.status -eq "failed") {
            throw "Phase 2 regression analysis failed"
        }
    }

    Assert-True ($Snapshot.status -eq "completed") "Phase 2 analysis timed out"
    Assert-True ($null -eq $Snapshot.result.alert_id) "Normal-day regression created alert"
}

Test-Step "Backend automated tests" {
    Set-Location $Backend

    [void](Invoke-Native `
        -File ".\.venv\Scripts\python.exe" `
        -Arguments @("-m", "pytest", "-q"))

    Set-Location $Root
}

Test-Step "Frontend typecheck and production build" {
    Set-Location $Frontend

    [void](Invoke-Native `
        -File "npm.cmd" `
        -Arguments @("run", "build"))

    Assert-True `
        (Test-Path (Join-Path $Frontend "dist\index.html")) `
        "Frontend production build missing"

    Set-Location $Root
}

Test-Step "Frontend evaluation metrics panel" {
    $FrontendResponse = Invoke-WebRequest `
        -Uri $FrontendBase `
        -UseBasicParsing `
        -TimeoutSec 15

    Assert-True ($FrontendResponse.StatusCode -eq 200) "Frontend did not load"

    $AppSource = Get-Content `
        (Join-Path $Frontend "src\App.tsx") `
        -Raw

    $ApiSource = Get-Content `
        (Join-Path $Frontend "src\api.ts") `
        -Raw

    Assert-True `
        ($AppSource -match "getEvaluation") `
        "Frontend does not load evaluation data"

    Assert-True `
        ($ApiSource -match "/api/v1/evaluation/report") `
        "Frontend API client lacks evaluation report endpoint"

    Assert-True `
        ($AppSource -match "Forecast") `
        "Frontend metrics panel lacks forecast display"

    Assert-True `
        ($AppSource -match "Anomaly") `
        "Frontend metrics panel lacks anomaly display"
}

Test-Step "Docker image and Compose validation" {
    [void](Invoke-Native `
        -File "docker" `
        -Arguments @("compose", "config", "--quiet"))

    $Images = Invoke-Native `
        -File "docker" `
        -Arguments @("compose", "config", "--images") `
        -Capture

    $Text = $Images -join "`n"

    Assert-True ($Text -match "phase3") "Compose does not reference Phase 3 images"
}

Test-Step "Runtime logs have no fatal errors" {
    $Since = $StartedAt.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

    $Logs = Invoke-Native `
        -File "docker" `
        -Arguments @(
            "compose",
            "logs",
            "--since",
            $Since,
            "backend",
            "worker"
        ) `
        -Capture

    $Text = $Logs -join "`n"

    Assert-True `
        ($Text -notmatch "Traceback \(most recent call last\)") `
        "Runtime traceback found"

    Assert-True `
        ($Text -notmatch '"level"\s*:\s*"ERROR"') `
        "Structured ERROR log found"
}

Test-Step "Secrets and generated test reports policy" {
    $TrackedSecrets = Invoke-Native `
        -File "git" `
        -Arguments @(
            "ls-files",
            "--",
            ".env",
            "backend/.env"
        ) `
        -Capture

    Assert-True `
        ([string]::IsNullOrWhiteSpace(($TrackedSecrets -join "").Trim())) `
        "Secret environment file is tracked"

    $Status = Invoke-Native `
        -File "git" `
        -Arguments @("status", "--short") `
        -Capture

    $StatusText = $Status -join "`n"

    Assert-True `
        ($StatusText -notmatch "(^|`n)\?\?\s+backend/\.env") `
        "backend/.env is untracked and exposed"
}

$FinishedAt = Get-Date
$Passed = @($Results | Where-Object { $_.Result -eq "PASS" })
$Failed = @($Results | Where-Object { $_.Result -eq "FAIL" })

Write-Host ""
Write-Host "PHASE 3 TEST SUMMARY" -ForegroundColor Cyan

$Results |
    Select-Object Test, Result, DurationMs, Detail |
    Format-Table -AutoSize -Wrap

$ReportFolder = Join-Path $Root "_test-reports"
New-Item -ItemType Directory -Path $ReportFolder -Force | Out-Null
$ReportPath = Join-Path $ReportFolder "phase3-$Stamp.txt"

$Lines = New-Object System.Collections.Generic.List[string]
$Lines.Add("SUPERAGENT SENTINEL - PHASE 3 TEST REPORT")
$Lines.Add("Started:  $($StartedAt.ToString('o'))")
$Lines.Add("Finished: $($FinishedAt.ToString('o'))")
$Lines.Add("API:      $ApiBase")
$Lines.Add("Frontend: $FrontendBase")
$Lines.Add("Passed:   $($Passed.Count)")
$Lines.Add("Failed:   $($Failed.Count)")
$Lines.Add("")

foreach ($Item in $Results) {
    $Lines.Add(
        ("{0,-5} | {1,-48} | {2,7} ms | {3}" -f `
            $Item.Result,
            $Item.Test,
            $Item.DurationMs,
            $Item.Detail)
    )
}

[System.IO.File]::WriteAllLines(
    $ReportPath,
    $Lines,
    (New-Object System.Text.UTF8Encoding($false))
)

Write-Host "Report: $ReportPath"

if ($Failed.Count -eq 0) {
    Write-Host ""
    Write-Host "ALL PHASE 3 TESTS PASSED ✅" -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "$($Failed.Count) PHASE 3 TEST(S) FAILED ❌" -ForegroundColor Red

foreach ($Item in $Failed) {
    Write-Host " - $($Item.Test): $($Item.Detail)" -ForegroundColor Red
}

exit 1
