<#
.SYNOPSIS
Read-only inventory of the live local ComfyUI node contracts and saved workflows.
Produces metadata ONLY; never copies prompts, song paths, tokens, or entire graphs.
Does not enqueue jobs, load checkpoints, call external APIs, or change BeatSync.
.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Inspect-GTRG-Local-Workflow.ps1
#>
[CmdletBinding()]
param(
    [string]$ComfyRoot = "$HOME\Downloads\ComfyUI-Setup\ComfyUI_windows_portable\ComfyUI",
    [ValidateRange(1, 150)][int]$MaxWorkflowFiles = 75
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$server = 'http://127.0.0.1:8188'
$repoRoot = Split-Path -Parent $PSScriptRoot
$reportDir = Join-Path $repoRoot 'outputs\gtrg_local_smoke'
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

function Get-PropertyNames([object]$object) {
    if ($null -eq $object) { return @() }
    return @($object.PSObject.Properties | ForEach-Object { $_.Name })
}
function Get-NodeNames([object]$document) {
    if ($null -eq $document) { return @() }
    $nodeProperty = $document.PSObject.Properties['nodes']
    if ($null -ne $nodeProperty -and $document.nodes -is [array]) {
        return @($document.nodes | ForEach-Object {
            if ($null -ne $_.PSObject.Properties['type']) { [string]$_.type }
            elseif ($null -ne $_.PSObject.Properties['class_type']) { [string]$_.class_type }
        } | Where-Object { $_ })
    }
    $candidate = $document
    if ($null -ne $document.PSObject.Properties['prompt'] -and
        $null -ne $document.prompt -and $document.prompt -isnot [string]) {
        $candidate = $document.prompt
    }
    $result = @()
    foreach ($property in $candidate.PSObject.Properties) {
        if ($null -ne $property.Value -and
            $null -ne $property.Value.PSObject.Properties['class_type']) {
            $result += [string]$property.Value.class_type
        }
    }
    return $result
}
function Get-SafeSummary([string]$source, [string]$label, [object[]]$names) {
    $asmo = @($names | Where-Object { $_ -match '^(AAO|ASMO)' })
    $ltx = @($names | Where-Object { $_ -match '(?i)LTX' })
    $gemma = @($names | Where-Object { $_ -match '(?i)gemma' })
    $providers = @($names | Where-Object { $_ -match '(?i)(api|render|savevideo|videocombine|vhs_)' })
    return [pscustomobject]@{
        source = $source
        name = $label
        nodes = $names.Count
        asmo_nodes = $asmo.Count
        ltx_nodes = $ltx.Count
        gemma_nodes = $gemma.Count
        possible_render_nodes = $providers.Count
        score = (3 * $asmo.Count) + (2 * $ltx.Count) + $gemma.Count
        class_types = @($names | Sort-Object -Unique)
    }
}

Write-Host '=== GTRG READ-ONLY WORKFLOW INVENTORY ===' -ForegroundColor Cyan
try {
    $null = Invoke-RestMethod -Uri "$server/system_stats" -TimeoutSec 5 -ErrorAction Stop
    $allInfo = Invoke-RestMethod -Uri "$server/object_info" -TimeoutSec 90 -ErrorAction Stop
}
catch { throw 'ComfyUI API is not available at 127.0.0.1:8188. Start ComfyUI first.' }
$available = Get-PropertyNames $allInfo
$contracts = @()
$interesting = @(
    'AAOInputs','AAOBeatTimeline','AAOBuildPlan','AAOValidatePlan',
    'AAOSelectScene','AAOSceneRenderInputs','AAOASMOMotionLoop',
    'AAOReview','AAOFeedback','AAONextPlan','AAOAssembleReel',
    'AAOCalibrateSync','AAOFinishScene','Gemma3SeedPrompt',
    'LocalGemmaFluxPrompts','LTXV23ModelsLoader','LTXV25ModelsLoader',
    'LTXV23ImgToVideo','LTXV25ImgToVideo','LTXAVTextEncoderLoader',
    'LtxApi25AudioToVideo','LtxApi25ImageToVideo','LTXVAudioVAELoader',
    'VHS_VideoCombine','SaveImage'
)
foreach ($name in $interesting) {
    $entry = $allInfo.PSObject.Properties[$name]
    if ($null -eq $entry) { continue }
    $def = $entry.Value
    $needed = @()
    $optional = @()
    $outputCount = 0
    $inputProperty = $def.PSObject.Properties['input']
    if ($null -ne $inputProperty -and $null -ne $inputProperty.Value) {
        $inputBlock = $inputProperty.Value
        $requiredProperty = $inputBlock.PSObject.Properties['required']
        $optionalProperty = $inputBlock.PSObject.Properties['optional']
        if ($null -ne $requiredProperty) {
            $needed = @(Get-PropertyNames $requiredProperty.Value)
        }
        if ($null -ne $optionalProperty) {
            $optional = @(Get-PropertyNames $optionalProperty.Value)
        }
    }
    $outputProperty = $def.PSObject.Properties['output']
    if ($null -ne $outputProperty -and $null -ne $outputProperty.Value) {
        $outputCount = @($outputProperty.Value).Count
    }
    $contracts += [pscustomobject]@{
        class_type = $name
        required_inputs = $needed
        optional_inputs = $optional
        output_count = $outputCount
    }
}
Write-Host "Node interfaces captured: $($contracts.Count)"

$userDir = Join-Path $ComfyRoot 'user'
$dirs = @()
if (Test-Path -LiteralPath $userDir -PathType Container) {
    $profiles = @(Get-ChildItem -LiteralPath $userDir -Directory -ErrorAction Stop)
    foreach ($profile in $profiles) {
        $wfDir = Join-Path $profile.FullName 'workflows'
        if (Test-Path -LiteralPath $wfDir -PathType Container) { $dirs += $wfDir }
    }
}
$workflowFiles = @()
foreach ($dir in $dirs) {
    $workflowFiles += @(Get-ChildItem -LiteralPath $dir -Filter '*.json' -File -Recurse -ErrorAction SilentlyContinue)
}
$workflowFiles = @($workflowFiles | Sort-Object LastWriteTime -Descending | Select-Object -First $MaxWorkflowFiles)
$summary = @()
$errors = @()
foreach ($file in $workflowFiles) {
    if ($file.Length -gt 15MB) {
        $errors += "$($file.Name): greater than 15 MB; skipped"
        continue
    }
    try {
        $doc = Get-Content -LiteralPath $file.FullName -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        $nodes = @(Get-NodeNames $doc)
        if ($nodes.Count -eq 0) { continue }
        $summary += Get-SafeSummary 'saved_workflow' $file.Name $nodes
    }
    catch {
        $errors += "$($file.Name): could not parse (content not included in report)"
    }
}

# History is read without exposing prompts or their input values.
# Not every ComfyUI version persists execution history after restart.
$historyCandidates = @()
try {
    $history = Invoke-RestMethod -Uri "$server/history?max_items=75" -TimeoutSec 30 -ErrorAction Stop
    foreach ($entry in $history.PSObject.Properties) {
        $item = $entry.Value
        if ($null -eq $item.PSObject.Properties['prompt']) { continue }
        $raw = @($item.prompt)
        if ($raw.Count -lt 3) { continue }
        $graph = $raw[2]
        $nodes = @(Get-NodeNames $graph)
        if ($nodes.Count -eq 0) { continue }
        $candidate = Get-SafeSummary 'execution_history' ([string]$entry.Name) $nodes
        if ($candidate.asmo_nodes -gt 0 -or $candidate.ltx_nodes -gt 0) {
            $historyCandidates += $candidate
        }
    }
}
catch {
    $errors += 'Could not read ComfyUI /history (saved workflow scan still completed)'
}

$summary = @($summary | Sort-Object score -Descending)
$historyCandidates = @($historyCandidates | Sort-Object score -Descending | Select-Object -First 20)
$best = @($summary + $historyCandidates | Sort-Object score -Descending | Select-Object -First 12)
$report = [ordered]@{
    timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
    comfy_ui_connected = $true
    available_registered_node_classes = $available.Count
    captured_node_contracts = $contracts
    saved_workflow_files_examined = $workflowFiles.Count
    saved_workflow_summaries = $summary
    history_workflow_summaries = $historyCandidates
    best_matches = $best
    scan_warnings = $errors
    no_gpu_render_started = $true
    contains_prompt_text = $false
    next_step = 'Inspect the top saved workflow and export its API format; do not send credentials or embedded prompts without reviewing.'
}
$output = Join-Path $reportDir 'gtrg_workflow_inventory.json'
$report | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $output -Encoding UTF8
Write-Host ''
Write-Host "Saved workflow JSONs checked: $($workflowFiles.Count)"
Write-Host "Historical ASMO/LTX executions found: $($historyCandidates.Count)"
Write-Host 'Top workflow candidates:'
$best | Select-Object -First 12 source, name, nodes, asmo_nodes, ltx_nodes, gemma_nodes |
    Format-Table -AutoSize
if ($best.Count -eq 0) {
    Write-Warning 'No saved workflow found. Save the current workflow in ComfyUI; do not send an empty or canary-only graph.'
}
Write-Host "Read-only inventory written to: $output" -ForegroundColor Green
Write-Host 'No graphs were queued; no Modal or paid video API calls were made.'
