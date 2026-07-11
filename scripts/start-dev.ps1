$Root = "D:\SUST-CSE-Carnival-2026\super-agent-platform"
Set-Location $Root
docker compose up -d postgres redis

$Backend = @"
Set-Location '$Root\backend'
& '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
"@
$Worker = @"
Set-Location '$Root\backend'
& '.\.venv\Scripts\python.exe' -m app.worker
"@
$Frontend = @"
Set-Location '$Root\frontend'
npm.cmd run dev -- --host 127.0.0.1
"@

Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $Backend
Start-Sleep -Seconds 2
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $Worker
Start-Sleep -Seconds 2
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $Frontend
Start-Sleep -Seconds 5
Start-Process "http://127.0.0.1:5173"
