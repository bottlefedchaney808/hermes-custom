@echo off
REM Launch the wrapper CLI with the repo's venv interpreter.
REM
REM PYTHONPATH points at the checkout so `from cli import HermesCLI` resolves —
REM cli.py lives at the repo root, not inside the installed package. HERMES_HOME
REM is already a user environment variable, so it is not set here; if you ever
REM move it, set it in this file rather than editing the repo.
REM
REM If you re-clone Hermes to a different path, this is the ONE line to update.

set "HERMES_CHECKOUT=C:\Users\bottl\.hermes\hermes-agent"

REM This wrapper exists ONLY to add MyCLI's prompt_toolkit sidebar, which lives
REM on the CLASSIC-CLI path -- cmd_chat exits into _launch_tui before
REM `from cli import main`, so under the Ink TUI the class swap never runs.
REM config.yaml has display.interface: tui, so a BARE call would resolve to
REM the TUI and drop the sidebar. Pin --cli unless the caller named one.
set "FORCE_CLI=--cli"
for %%A in (%*) do (
    if /I "%%~A"=="--tui" set "FORCE_CLI="
    if /I "%%~A"=="--cli" set "FORCE_CLI="
)

set "PYTHONPATH=%HERMES_CHECKOUT%;%PYTHONPATH%"
"%HERMES_CHECKOUT%\venv\Scripts\python.exe" "%~dp0my_cli.py" %FORCE_CLI% %*
