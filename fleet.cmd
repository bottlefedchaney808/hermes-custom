@echo off
REM The fleet CLI - declarative install management for this box's Hermes profiles.
REM Uses a dedicated venv so PyYAML / ruamel.yaml resolve. Created 2026-10-03 to
REM replace the dead ~/.hermes/hermes-agent/venv path (which does not exist here).
set "FLEET_VENV=C:\Users\bottl\AppData\Local\hermes\hermes-custom-venv\Scripts\python.exe"
"%FLEET_VENV%" -m fleet.cli %*
