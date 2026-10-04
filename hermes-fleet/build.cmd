@echo off
REM Build both UI halves from one source tree in ui-src/.
REM
REM   desktop/plugin.js        ESM, loaded by the Hermes Desktop plugin loader
REM   dashboard/dist/index.js  IIFE, loaded by the web dashboard
REM
REM esbuild comes from the Hermes checkout, so there is nothing to npm install.
REM Commit both artifacts: every host loads the built file, never the sources.
setlocal
set "ESB=C:\Users\bottl\AppData\Local\hermes\tools\node-26.7.0-win32-x64\esbuild.exe"
if not exist "%ESB%" (
  echo esbuild not found at %ESB%
  echo Re-point this file, or run: npm install
  exit /b 1
)
pushd "%~dp0"
"%ESB%" ui-src/plugin.tsx --bundle --format=esm --platform=browser --jsx=automatic ^
  --external:@hermes/plugin-sdk --external:react --external:react/jsx-runtime ^
  --outfile=desktop/plugin.js || goto :fail
"%ESB%" ui-src/dashboard.tsx --bundle --format=iife --platform=browser --jsx=automatic ^
  --alias:react=./ui-src/shims/react.ts --alias:react/jsx-runtime=./ui-src/shims/jsx-runtime.ts ^
  --outfile=dashboard/dist/index.js || goto :fail
popd
echo Built both halves.
exit /b 0
:fail
popd
echo Build failed.
exit /b 1
