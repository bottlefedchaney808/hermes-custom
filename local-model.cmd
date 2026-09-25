@echo off
REM See / unload / stop the managed llama-server (local model weights on the GPU).
REM   local-model            status
REM   local-model unload     free VRAM, keep the router warm
REM   local-model stop       unload, then terminate the router
REM Uses the Hermes venv python so psutil is available for the process-tree walk.
set "HERMES_CHECKOUT=C:\Users\bottl\.hermes\hermes-agent"
"%HERMES_CHECKOUT%\venv\Scripts\python.exe" "%~dp0local_model.py" %*
