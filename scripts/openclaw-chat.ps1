param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Message,

    [string]$Service = "openclaw-default",

    [string]$ComposeFile = "lobstergym/docker-compose.yml",

    [string]$To = "+15555550123",

    [switch]$RawJson
)

$ErrorActionPreference = "Stop"

function Quote-Arg {
    param([string]$Value)

    if ($null -eq $Value) {
        return '""'
    }

    if ($Value -match '[\s"]') {
        return '"' + ($Value -replace '"', '\"') + '"'
    }

    return $Value
}

if (-not (Test-Path -LiteralPath $ComposeFile)) {
    throw "Compose file not found: $ComposeFile"
}

$runningServices = & docker compose -f $ComposeFile ps --services --status running
if ($LASTEXITCODE -ne 0) {
    throw "Failed to query Docker Compose services."
}

$runningServiceList = @($runningServices | Where-Object { $_ -and $_.Trim() })
if ($Service -notin $runningServiceList) {
    throw "Service '$Service' is not running. Start it with: docker compose -f $ComposeFile up -d $Service"
}

try {
    $stdoutFile = [System.IO.Path]::GetTempFileName()
    $stderrFile = [System.IO.Path]::GetTempFileName()

    $dockerCommand = (Get-Command docker).Source
    $argumentString = @(
        'compose',
        '-f', (Quote-Arg $ComposeFile),
        'exec',
        '-T',
        (Quote-Arg $Service),
        'openclaw',
        'agent',
        '--local',
        '--to', (Quote-Arg $To),
        '--json',
        '--message', (Quote-Arg $Message)
    ) -join ' '

    $process = Start-Process -FilePath $dockerCommand -ArgumentList $argumentString -Wait -PassThru -NoNewWindow -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
    $exitCode = $process.ExitCode

    $raw = if (Test-Path -LiteralPath $stdoutFile) {
        Get-Content -LiteralPath $stdoutFile -Raw
    }
    else {
        ""
    }

    $stderr = if (Test-Path -LiteralPath $stderrFile) {
        Get-Content -LiteralPath $stderrFile -Raw
    }
    else {
        ""
    }

    if ($exitCode -ne 0) {
        throw "OpenClaw command failed.`n$stderr`n$raw"
    }

    if ([string]::IsNullOrWhiteSpace($raw)) {
        throw "OpenClaw returned an empty response.`n$stderr"
    }

    $jsonStart = $raw.IndexOf('{')
    if ($jsonStart -lt 0) {
        throw "Could not find JSON in OpenClaw output.`n$raw"
    }

    $json = $raw.Substring($jsonStart).Trim()

    if ($RawJson) {
        $json
        return
    }

    $data = $json | ConvertFrom-Json
    $agentMeta = $data.meta.agentMeta
    $payloadText = $null

    if ($data.payloads -and $data.payloads.Count -gt 0) {
        $payloadText = $data.payloads[0].text
    }

    "service:    $Service"
    if ($agentMeta.sessionId) {
        "sessionId:  $($agentMeta.sessionId)"
    }
    if ($agentMeta.model) {
        "model:      $($agentMeta.model)"
    }
    if ($agentMeta.provider) {
        "provider:   $($agentMeta.provider)"
    }

    if ($payloadText) {
        ""
        $payloadText
    }
    else {
        $json
    }
}
finally {
    if ($stdoutFile) {
        Remove-Item -LiteralPath $stdoutFile -ErrorAction SilentlyContinue
    }
    if ($stderrFile) {
        Remove-Item -LiteralPath $stderrFile -ErrorAction SilentlyContinue
    }
}
