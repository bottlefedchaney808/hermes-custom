# Windows PowerShell equivalent of stop-server.sh
# Stops the brainstorming visual-companion Node server for a given session dir
# and cleans up its state (only deleting ephemeral temp dirs).
#
# Usage:
#   .\stop-server.ps1 <session_dir>
#
# The <session_dir> is the value of screen_dir/state_dir's parent as reported by
# start-server.ps1 (the directory that contains a `state` subfolder).
param(
    [Parameter(Mandatory = $true)][string]$SessionDir
)

$ErrorActionPreference = "Stop"
$StateDir     = Join-Path $SessionDir "state"
$PidFile      = Join-Path $StateDir "server.pid"
$ServerIdFile = Join-Path $StateDir "server-instance-id"
$StoppedFile  = Join-Path $StateDir "server-stopped"
$InfoFile     = Join-Path $StateDir "server-info"

function Mark-Stopped([string]$reason) {
    Remove-Item $InfoFile -ErrorAction SilentlyContinue
    $ts = [int][System.DateTimeOffset]::Now.ToUnixTimeSeconds()
    $json = "{`"reason`":`"$reason`",`"timestamp`":$ts}`
    [System.IO.File]::WriteAllText($StoppedFile, $json)
}

function Read-ExpectedServerId {
    if (-not (Test-Path $ServerIdFile)) { return $null }
    $id = (Get-Content $ServerIdFile -ErrorAction SilentlyContinue).Trim()
    if ($id -match '^[A-Za-z0-9_-]{32,64}$') { return $id }
    return $null
}

# Confirm a PID is our server by matching --brainstorm-server-id in its cmdline.
function Test-IsOurServer([int]$pid, [string]$expectedId) {
    if (-not $expectedId) { return $false }
    $expectedArg = "--brainstorm-server-id=$expectedId"
    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $pid" -ErrorAction Stop
        if ($null -eq $proc) { return $false }
        return ($proc.CommandLine -like "*$expectedArg*")
    } catch {
        return $false
    }
}

if (Test-Path $PidFile) {
    $pid = [int](Get-Content $PidFile -ErrorAction SilentlyContinue)
    $expectedId = Read-ExpectedServerId
    if ($pid -and -not (Test-IsOurServer $pid $expectedId)) {
        # Refuse to signal a PID we can't prove is our server (stale pid file).
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        Remove-Item $ServerIdFile -ErrorAction SilentlyContinue
        Mark-Stopped "stale_pid"
        Write-Host '{"status": "stale_pid"}'
        exit 0
    }

    # Try graceful stop, then force.
    try { Stop-Process -Id $pid -ErrorAction SilentlyContinue } catch {}
    for ($i = 0; $i -lt 20; $i++) {
        $alive = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($null -eq $alive) { break }
        Start-Sleep -Milliseconds 100
    }
    $alive = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($null -ne $alive) {
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 100
    }
    $alive = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($null -ne $alive) {
        Write-Host '{"status": "failed", "error": "process still running"}'
        exit 1
    }

    Remove-Item $PidFile      -ErrorAction SilentlyContinue
    Remove-Item $ServerIdFile -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $StateDir "server.log") -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $StateDir "server.log.err") -ErrorAction SilentlyContinue
    Mark-Stopped "stop-server.ps1"

    # Only delete ephemeral session dirs under the OS temp dir.
    $tmpRoot = $env:TMP
    if ($tmpRoot -and $SessionDir.StartsWith($tmpRoot, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item $SessionDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    Write-Host '{"status": "stopped"}'
} else {
    Write-Host '{"status": "not_running"}'
}
