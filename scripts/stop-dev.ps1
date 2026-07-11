foreach($Port in @(8000,5173)){
  $Connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  foreach($Connection in $Connections){ Stop-Process -Id $Connection.OwningProcess -Force -ErrorAction SilentlyContinue }
}