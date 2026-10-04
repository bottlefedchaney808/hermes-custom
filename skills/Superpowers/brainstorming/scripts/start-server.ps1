# Windows PowerShell equivalent of start-server.sh
# Starts the brainstorming visual-companion Node server and prints the
# server-started JSON (with URL + key) to stdout.
#
# Usage:
#   .\start-server.ps1 [-ProjectDir <path>] [-BindHost <bind>] [-UrlHost <display>]
#                      [-IdleTimeoutMinutes <n>] [-Open]
#
# The server binds to 127.0.0.1 by default and self-terminates after the idle
# timeout. Pass -ProjectDir to persist session files under <ProjectDir>/.superpowers/.
param(
    [string]$ProjectDir = "",
    [string]$BindHost = "127.0.0.1",
    [string]$UrlHost = "",
    [int]$IdleTimeoutMinutes = 0,
    [switch]$Open
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# Resolve node. Prefer PATH, then the Hermes-bundled node.
$node = (Get-Command node -ErrorAction SilentlyContinue | Select-Object -First 1)
if ($null -eq $node) {
    $bundled = Join-Path $env:LOCALAPPDATA "hermes\tools"
    $candidate = Get-ChildItem -Path $bundled -Recurse -Filter "node.exe" -ErrorAction SilentlyContinue |
                 Select-Object -First 1
    if ($candidate) { $node = $candidate.FullName }
}
if ($null -eq $node) {
    Write-Error '{"error": "node not found on PATH or under %LOCALAPPDATA%\hermes\tools"}'
    exit 1
}

# Determine display host
if ([string]::IsNullOrEmpty($UrlHost)) {
    if ($BindHost -eq "127.0.0.1" -or $BindHost -eq "localhost") { $UrlHost = "localhost" }
    else { $UrlHost = $BindHost }
}

# Session directory: persistent under ProjectDir, else OS temp dir.
$unixNow = [int][System.DateTimeOffset]::Now.ToUnixTimeSeconds()
$sessionId = "$([System.Diagnostics.Process]::GetCurrentProcess().Id)-$unixNow"
if ([string]::IsNullOrEmpty($ProjectDir)) {
    $base = Join-Path $env:TMP "brainstorm"
    $sessionDir = Join-Path $base "$sessionId"
} else {
    $sessionDir = Join-Path (Join-Path $ProjectDir ".superpowers\brainstorm") $sessionId
}
$contentDir = Join-Path $sessionDir "content"
$stateDir   = Join-Path $sessionDir "state"
New-Item -ItemType Directory -Path $contentDir -Force | Out-Null
New-Item -ItemType Directory -Path $stateDir   -Force | Out-Null
$pidFile       = Join-Path $stateDir "server.pid"
$logFile       = Join-Path $stateDir "server.log"
$serverIdFile  = Join-Path $stateDir "server-instance-id"

# Per-start instance id (32-64 alphanumeric chars) so stop-server can verify the PID.
$serverId = -join ((1..48) | ForEach-Object { [char](0x30 + (Get-Random -Maximum 10)) })
[System.IO.File]::WriteAllText($serverIdFile, $serverId)

# Kill a prior instance for this exact session dir if present.
if (Test-Path $pidFile) {
    $oldPid = [int](Get-Content $pidFile -ErrorAction SilentlyContinue)
    if ($oldPid) { Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue }
    Remove-Item $pidFile -ErrorAction SilentlyContinue
}

# Build environment for the node child process.
$env:BRAINSTORM_DIR = $sessionDir
$env:BRAINSTORM_HOST = $BindHost
$env:BRAINSTORM_URL_HOST = $UrlHost
$env:BRAINSTORM_OWNER_PID = ""   # empty -> owner-pid watchdog disabled on Windows
if ($IdleTimeoutMinutes -ge 1) {
    $env:BRAINSTORM_IDLE_TIMEOUT_MS = ($IdleTimeoutMinutes * 60 * 1000).ToString()
}
if ($Open) { $env:BRAINSTORM_OPEN = "1" }

$proc = Start-Process -FilePath $node `
    -ArgumentList @("server.cjs", "--brainstorm-server-id=$serverId") `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError  "$logFile.err" `
    -PassThru -NoNewWindow
$proc.Id | Out-File -FilePath $pidFile -Encoding ascii

# Poll the log for the server-started line.
$started = $null
for ($i = 0; $i -lt 50; $i++) {
    if ((Get-Content $logFile -ErrorAction SilentlyContinue | Select-String "server-started")) {
        $started = (Get-Content $logFile | Select-String "server-started" | Select-Object -First 1).Line
        break
    }
    Start-Sleep -Milliseconds 100
}

if ($null -eq $started) {
    Write-Host '{"error": "Server failed to start within 5 seconds"}'
    exit 1
}
Write-Host $started
exit 0
