param(
    [int]$HttpPort = 8080,
    [int]$TcpPort = 5000,
    [string]$Database = "data/star_topology.sqlite3"
)

$env:STAR_TOPOLOGY_TCP_HOST = "0.0.0.0"
$env:STAR_TOPOLOGY_TCP_PORT = "$TcpPort"
$env:STAR_TOPOLOGY_DB_PATH = $Database
Set-Location "$PSScriptRoot\.."
& "$PSScriptRoot\..\.venv\Scripts\python.exe" -m uvicorn server.main:create_app --factory --host 0.0.0.0 --port $HttpPort
