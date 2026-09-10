@echo off
REM Deploy brain-rag to EVERY profile root that should have it.
REM The desktop/agent plugin root is profile-scoped: copying only the global
REM root leaves named profiles running a stale copy with no error anywhere.

setlocal
set SRC=%~dp0..
set ROOTS=%LOCALAPPDATA%\hermes\plugins\brain-rag
set ROOTS=%ROOTS%;%LOCALAPPDATA%\hermes\profiles\local-agent\plugins\brain-rag

for %%R in ("%ROOTS:;=" "%") do (
    echo Deploying to %%~R
    if not exist "%%~R" mkdir "%%~R"
    xcopy /Y /E /I /Q "%SRC%\plugin\*" "%%~R\" >nul
    if not exist "%%~R\vendor\src" mkdir "%%~R\vendor\src"
    xcopy /Y /E /I /Q "%SRC%\src\*" "%%~R\vendor\src\" >nul
)

echo.
echo Deployed. Two more steps, both required:
echo   1. Add brain-rag to plugins.enabled in EACH profile's config.yaml.
echo      Desktop Settings -^> Plugins does NOT import the Python half;
echo      without plugins.enabled every ctx.rest call answers 405.
echo   2. Restart the supervised backend so the routes mount
echo      (route mounts happen at process import; a rescan does not remount).
endlocal
