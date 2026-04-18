@echo off
echo Starting Kobold Sandbox...
start "Server :5002" cmd /c "%~dp0start-server.cmd"
timeout /t 3 /nobreak >nul
start "TSX :5173" cmd /c "%~dp0start-tsx.cmd"
echo.
echo Server: http://localhost:5002/pipeline-chat
echo TSX:    http://localhost:5173/
