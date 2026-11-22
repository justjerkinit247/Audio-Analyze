<#
.SYNOPSIS
Starts an existing local ComfyUI installation if needed and runs a tiny 9:16 canary.
No model downloads, external paid video API, or Modal/GPU-cloud interaction.
#>
[CmdletBinding()]
param(
    [switch]$NoStart,
    [ValidateRange(10, 300)][int]$StartupTimeoutSeconds = 150,
    [ValidateRange(10, 180)][int]$JobTimeoutSeconds = 90
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:8188'
$repoRoot = Split-Path -Parent $PSScriptRoot
$reportDir = Join-Path $repoRoot 'outputs\gtrg_local_smoke'
New-Item -ItemType Directory -Path $reportDir -Force | Out-Null

function Get-ComfyStats {
    try { return Invoke-RestMethod -Uri "$base/system_stats" -TimeoutSec 4 -ErrorAction Stop }
    catch { return $null }
}

Write-Host '=== LOCAL GTRG COMFYUI PREFLIGHT ===' -ForegroundColor Cyan
$stats = Get-ComfyStats
if ($null -eq $stats) {
    if ($NoStart) { throw 'ComfyUI is not responding at port 8188 and -NoStart was specified.' }
    $candidates = @(
        (Join-Path $HOME 'Downloads\ComfyUI-Setup\ComfyUI_windows_portable'),
        (Join-Path $HOME 'Downloads\ComfyUI_windows_portable'),
        (Join-Path $HOME 'Documents\ComfyUI_windows_portable')
    )
    $portable = $candidates | Where-Object {
        Test-Path -LiteralPath (Join-Path $_ 'run_nvidia_gpu.bat') -PathType Leaf
    } | Select-Object -First 1
    if (-not $portable) { throw ('Existing ComfyUI portable launcher not found. Checked: ' + ($candidates -join '; ')) }
    $launcher = Join-Path $portable 'run_nvidia_gpu.bat'
    Write-Host "Launching existing ComfyUI: $launcher"
    $arguments = '/k ""{0}""' -f $launcher
    Start-Process -FilePath 'cmd.exe' -ArgumentList $arguments -WorkingDirectory $portable | Out-Null
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        $stats = Get-ComfyStats
        if ($null -ne $stats) { break }
    }
}
if ($null -eq $stats) { throw 'ComfyUI did not start. Inspect its console for the actual startup error.' }

Write-Host 'ComfyUI API online.' -ForegroundColor Green
$devices = @($stats.devices | ForEach-Object { [string]$_.name })
Write-Host ('Devices: ' + ($devices -join '; '))
$info = Invoke-RestMethod -Uri "$base/object_info" -TimeoutSec 90 -ErrorAction Stop
$classes = @($info.PSObject.Properties.Name)
foreach ($required in @('EmptyImage', 'SaveImage')) {
    if ($required -notin $classes) { throw "Missing built-in ComfyUI node: $required" }
}
$relevant = @($classes | Where-Object { $_ -match '(?i)(AAO|ASMO|LTX|Gemma)' } | Sort-Object)
$relevant | Set-Content -LiteralPath (Join-Path $reportDir 'registered_gtrg_nodes.txt') -Encoding UTF8
Write-Host ('GTRG-related node classes: ' + $relevant.Count)
$relevant | Select-Object -First 70 | ForEach-Object { Write-Host "  $_" }
$loopFound = 'AAOASMOMotionLoop' -in $classes
if (-not $loopFound) { Write-Warning 'AAOASMOMotionLoop not registered; full ASMO workflow requires investigation.' }

$queue = Invoke-RestMethod -Uri "$base/queue" -TimeoutSec 15 -ErrorAction Stop
$running = 0
$pending = 0
if ($null -ne $queue.queue_running) { $running = @($queue.queue_running).Count }
if ($null -ne $queue.queue_pending) { $pending = @($queue.queue_pending).Count }
if ($running -gt 0 -or $pending -gt 0) {
    throw "ComfyUI queue is busy: running=$running pending=$pending. Refusing to interrupt or enqueue."
}

# Built-in EmptyImage -> SaveImage only, 288x512 exactly 9:16.
$prompt = @{
    '1' = @{ class_type = 'EmptyImage'; inputs = @{ width = 288; height = 512; batch_size = 1 } }
    '2' = @{ class_type = 'SaveImage'; inputs = @{ images = @('1', 0); filename_prefix = 'GTRG_Local_Canary' } }
}
$payload = @{ prompt = $prompt; client_id = ([guid]::NewGuid().ToString()) } | ConvertTo-Json -Depth 20 -Compress
$response = Invoke-RestMethod -Uri "$base/prompt" -Method Post -ContentType 'application/json' -Body $payload -TimeoutSec 20 -ErrorAction Stop
if (-not $response.prompt_id) { throw 'ComfyUI did not accept the canary graph.' }
$promptId = [string]$response.prompt_id
$imageInfo = $null
$deadline = (Get-Date).AddSeconds($JobTimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    $history = Invoke-RestMethod -Uri "$base/history/$promptId" -TimeoutSec 15 -ErrorAction Stop
    $property = $history.PSObject.Properties[$promptId]
    if ($null -eq $property) { continue }
    $result = $property.Value
    if ($result.status.status_str -in @('error', 'failed')) { throw "Local canary execution error: $promptId" }
    $saved = $result.outputs.PSObject.Properties['2']
    if ($null -ne $saved -and $null -ne $saved.Value.images) {
        $imageInfo = @($saved.Value.images) | Select-Object -First 1
        if ($null -ne $imageInfo -and $imageInfo.filename) { break }
    }
    if ($result.status.completed) { throw "Canary completed without SaveImage output: $promptId" }
}
if ($null -eq $imageInfo -or -not $imageInfo.filename) { throw "Canary timed out, prompt ID: $promptId" }
$name = [uri]::EscapeDataString([string]$imageInfo.filename)
$subfolder = [uri]::EscapeDataString([string]$imageInfo.subfolder)
$viewUrl = "$base/view?filename=$name&subfolder=$subfolder&type=output"
$imageFile = Join-Path $reportDir 'GTRG_local_canary.png'
Invoke-WebRequest -Uri $viewUrl -OutFile $imageFile -UseBasicParsing -TimeoutSec 25 -ErrorAction Stop | Out-Null
$bytes = [System.IO.File]::ReadAllBytes($imageFile)
$sig = @(137,80,78,71,13,10,26,10)
if ($bytes.Length -lt 100) { throw 'Canary image output unexpectedly small.' }
for ($j = 0; $j -lt $sig.Count; $j++) {
    if ([int]$bytes[$j] -ne $sig[$j]) { throw 'Canary output has invalid PNG signature.' }
}

$sha256 = (Get-FileHash -LiteralPath $imageFile -Algorithm SHA256).Hash
$summary = [ordered]@{
    timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
    server_url = $base
    device_names = $devices
    asmo_loop_registered = $loopFound
    related_node_class_count = $relevant.Count
    prompt_id = $promptId
    image_size = '288x512 (9:16)'
    image_file = $imageFile
    image_sha256 = $sha256
    cloud_calls = 0
    scope = 'Native local canary only; real LTX workflow still unverified'
}
$summaryPath = Join-Path $reportDir 'local_canary_result.json'
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryPath -Encoding UTF8

Write-Host 'LOCAL CANARY PASSED.' -ForegroundColor Green
Write-Host "Output image: $imageFile"
Write-Host "Report: $summaryPath"
Write-Host "ASMO loop registered: $loopFound"
Write-Host 'No Modal or external API calls were made.'
Start-Process $base | Out-Null
