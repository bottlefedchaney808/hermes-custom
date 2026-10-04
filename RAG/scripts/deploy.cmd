@echo off
REM Deploy brain-rag to EVERY profile root that should have it.
REM The desktop/agent plugin root is profile-scoped: copying only the global
REM root leaves named profiles running a stale copy with no error anywhere.
REM
REM Override destinations with BRAIN_RAG_DEPLOY_ROOTS (semicolon-separated).
REM Override source repo root with BRAIN_RAG_DEPLOY_SRC.
REM Tests must set both to tmp paths — never copy into live LocalAppData.

setlocal
if not defined BRAIN_RAG_DEPLOY_SRC set "BRAIN_RAG_DEPLOY_SRC=%~dp0.."
set "SRC=%BRAIN_RAG_DEPLOY_SRC%"

if defined BRAIN_RAG_DEPLOY_ROOTS goto roots_from_env
set "ROOTS=%LOCALAPPDATA%\hermes\plugins\brain-rag"
set "ROOTS=%ROOTS%;%LOCALAPPDATA%\hermes\profiles\local-agent\plugins\brain-rag"
set "ROOTS=%ROOTS%;%LOCALAPPDATA%\hermes\profiles\coder\plugins\brain-rag"
goto roots_ready
:roots_from_env
set "ROOTS=%BRAIN_RAG_DEPLOY_ROOTS%"
:roots_ready

set "EXCL=%~dp0deploy-exclude.txt"

for %%R in ("%ROOTS:;=" "%") do (
    echo Deploying to %%~R
    if not exist "%%~R" mkdir "%%~R"
    if errorlevel 1 goto :mkdir_fail
    xcopy /Y /E /I /Q /EXCLUDE:%EXCL% "%SRC%\plugin\*" "%%~R\" >nul
    if errorlevel 1 goto :plugin_fail
    if not exist "%%~R\vendor\src" mkdir "%%~R\vendor\src"
    if errorlevel 1 goto :mkdir_fail
    xcopy /Y /E /I /Q /EXCLUDE:%EXCL% "%SRC%\src\*" "%%~R\vendor\src\" >nul
    if errorlevel 1 goto :vendor_fail
)

echo.
echo Deployed. Two more steps, both required:
echo   1. Add brain-rag to plugins.enabled in EACH profile's config.yaml.
echo      Desktop Settings -^> Plugins does NOT import the Python half;
echo      without plugins.enabled every ctx.rest call answers 405.
echo   2. Restart the supervised backend so the routes mount
echo      (route mounts happen at process import; a rescan does not remount).
endlocal
exit /b 0

:mkdir_fail
echo ERROR: could not create destination directory
exit /b 1

:plugin_fail
echo ERROR: plugin copy failed
exit /b 1

:vendor_fail
echo ERROR: vendor src copy failed
exit /b 1
