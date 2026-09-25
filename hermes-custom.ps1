<#
.SYNOPSIS
    Launch the Hermes wrapper CLI with the repo's venv interpreter.

.DESCRIPTION
    PowerShell port of hermes-custom.cmd.

    PYTHONPATH points at the Hermes checkout so `from cli import HermesCLI`
    resolves -- cli.py lives at that repo's root, not inside the installed
    package. HERMES_HOME is already a user environment variable, so it is not
    set here; if you ever move it, set it in this file rather than editing the
    repo.

    If you re-clone Hermes to a different path, $HermesCheckout below is the ONE
    thing to update (or set the HERMES_CHECKOUT environment variable).

.EXAMPLE
    .\hermes-custom.ps1 --help

.EXAMPLE
    hermes chat "what's up"
#>

# No param() block on purpose: it would let PowerShell steal arguments that
# belong to the Python CLI (-Verbose, -Debug, -ea, ambiguous prefixes, ...).
# With no param block every token lands in $args untouched.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Env var wins so you can point at another checkout without editing the file.
$HermesCheckout = if ($env:HERMES_CHECKOUT) {
    $env:HERMES_CHECKOUT
} else {
    'C:\Users\bottl\.hermes\hermes-agent'
}

$python = Join-Path $HermesCheckout 'venv\Scripts\python.exe'
$cli    = Join-Path $PSScriptRoot 'my_cli.py'

if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "Hermes venv interpreter not found: $python`nSet `$env:HERMES_CHECKOUT or edit `$HermesCheckout in $PSCommandPath."
    exit 1
}
if (-not (Test-Path -LiteralPath $cli)) {
    Write-Error "Wrapper CLI not found: $cli"
    exit 1
}

# This wrapper exists ONLY to add MyCLI's prompt_toolkit sidebar, and that
# lives on the CLASSIC-CLI path: cmd_chat hands off to _launch_tui() and
# sys.exit()s before `from cli import main`, so under the Ink TUI the class
# swap never runs and the sidebar silently vanishes.
#
# config.yaml now has `display.interface: tui`, which makes a BARE invocation
# resolve to the TUI (_resolve_use_tui rule 5). So pin --cli to keep the
# wrapper doing its one job -- unless the caller explicitly asked otherwise,
# in which case their flag is left to win on its own.
$forwarded = @($args)
if (-not ($forwarded | Where-Object { $_ -eq '--tui' -or $_ -eq '--cli' })) {
    $forwarded = @('--cli') + $forwarded
}

# Prepend the checkout to PYTHONPATH for this call only, then put it back --
# the script runs in the caller's process, so an unrestored change would leak
# into the rest of the session.
$code = 0
$savedPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = if ($savedPythonPath) {
        "$HermesCheckout;$savedPythonPath"
    } else {
        $HermesCheckout
    }

    # Ctrl-C / a nonzero exit from Python must not be treated as a PS error.
    $ErrorActionPreference = 'Continue'
    & $python $cli @forwarded
    $code = $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $savedPythonPath
}

exit $code
