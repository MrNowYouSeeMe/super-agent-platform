$Ports = @(8000, 5173)
foreach ($Port in $Ports) {
    $Connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($Connection in $Connections) {
        Stop-Process -Id $Connection.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}
Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like "*app.worker*" -and $_.Name -like "python*"
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
