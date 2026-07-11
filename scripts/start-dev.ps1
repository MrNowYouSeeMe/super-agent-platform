$Root = "D:\SUST-CSE-Carnival-2026\super-agent-platform"
$BackendCommand = "Set-Location '$Root\backend'; & '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
$FrontendCommand = "Set-Location '$Root\frontend'; npm.cmd run dev -- --host 127.0.0.1"
Start-Process powershell.exe -ArgumentList "-NoExit","-Command",$BackendCommand
Start-Sleep -Seconds 2
Start-Process powershell.exe -ArgumentList "-NoExit","-Command",$FrontendCommand
Start-Sleep -Seconds 5
Start-Process "http://127.0.0.1:5173"