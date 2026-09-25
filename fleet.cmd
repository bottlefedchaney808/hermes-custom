@echo off
REM The fleet CLI — declarative install management across all three Hermes
REM profiles. Uses the Hermes venv so PyYAML and the evolution package resolve.
REM
REM   fleet status            what is installed where, and what drifted
REM   fleet sync              dry run
REM   fleet sync --apply      make the disk match fleet.yaml
REM
REM If you re-clone Hermes to a different path, this is the ONE line to update.
set "HERMES_CHECKOUT=C:\Users\bottl\.hermes\hermes-agent"
"%HERMES_CHECKOUT%\venv\Scripts\python.exe" -m fleet.cli %*
