@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

set "ROOT="
set "NO_BROWSER="

:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="-NoBrowser" (
    set "NO_BROWSER=1"
    shift
    goto parse_args
)
if /i "%~1"=="--no-browser" (
    set "NO_BROWSER=1"
    shift
    goto parse_args
)
if not defined ROOT (
    set "ROOT=%~1"
)
shift
goto parse_args

:args_done
if not defined ROOT set "ROOT=%REPO_ROOT%"

set "HOST=127.0.0.1"
set "PORT=5002"
set "HEALTH_URL=http://%HOST%:%PORT%/health"
set "REACTIVE_URL=http://%HOST%:%PORT%/reactive-chat?ts=%RANDOM%%RANDOM%"

echo Restarting kobold-sandbox on port %PORT%...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { if ($_ -and $_ -ne $PID) { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } }"

echo Waiting for %HEALTH_URL% ...
set "KOBOLD_SANDBOX_ROOT=%ROOT%"
start "" "%REPO_ROOT%\serve-5002.cmd"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$deadline = (Get-Date).AddSeconds(30); while ((Get-Date) -lt $deadline) { try { $response = Invoke-RestMethod -Uri '%HEALTH_URL%' -Method Get -TimeoutSec 2; if ($response.ok -eq $true) { exit 0 } } catch {} Start-Sleep -Milliseconds 750 }; exit 1"

if errorlevel 1 (
    echo Server did not become healthy within 30s: %HEALTH_URL%
    exit /b 1
)

echo Server is up: %HEALTH_URL%
if not defined NO_BROWSER (
    start "" "%REACTIVE_URL%"
    echo Opened: %REACTIVE_URL%
)
