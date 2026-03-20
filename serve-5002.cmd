@echo off
REM Start kobold-sandbox API server on port 5002,
REM connecting to KoboldCPP backend at localhost:5001.
REM
REM Usage:
REM   serve-5002.cmd              (use script dir as sandbox root)
REM   serve-5002.cmd C:\path\to   (use custom sandbox root)

setlocal

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

if "%~1"=="" (
    set "ROOT=%SCRIPT_DIR%"
) else (
    set "ROOT=%~1"
)

set "HOST=127.0.0.1"
set "PORT=5002"
set "KOBOLD_URL=http://localhost:5001"

if not exist "%ROOT%\.sandbox\state.json" (
    echo Sandbox not initialised in %ROOT% — running init...
    set "PYTHONPATH=%SCRIPT_DIR%\src"
    python -m kobold_sandbox.cli init --root "%ROOT%" --kobold-url "%KOBOLD_URL%"
)

echo Starting kobold-sandbox server on http://%HOST%:%PORT%
echo KoboldCPP backend: %KOBOLD_URL%
echo Sandbox root: %ROOT%
echo ---

set "PYTHONPATH=%SCRIPT_DIR%\src"
python -c "import os,uvicorn;from kobold_sandbox.server import create_app;uvicorn.run(create_app(r'%ROOT%'),host='%HOST%',port=%PORT%)"
