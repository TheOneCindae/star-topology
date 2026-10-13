param(
    [Parameter(Mandatory = $true)][int]$NodeId,
    [Parameter(Mandatory = $true)][string]$HubHost,
    [int]$HubPort = 5000,
    [int]$SendTo = 0,
    [string]$Message = "",
    [double]$TrafficIntervalMs = 0,
    [int]$TrafficCount = 0
)

$arguments = @("-m", "client.main", "--id", "$NodeId", "--host", $HubHost, "--port", "$HubPort")
if ($SendTo -gt 0) {
    $arguments += @("--send-to", "$SendTo", "--message", $Message)
}
if ($TrafficIntervalMs -gt 0) {
    $arguments += @("--traffic-interval-ms", "$TrafficIntervalMs", "--traffic-count", "$TrafficCount")
}
Set-Location "$PSScriptRoot\.."
& "$PSScriptRoot\..\.venv\Scripts\python.exe" @arguments
