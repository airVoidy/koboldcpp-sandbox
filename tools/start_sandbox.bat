@echo off
cd /d "%~dp0\.."
echo Starting Kobold Sandbox on port 5002...
python -c "import uvicorn; from kobold_sandbox.server import create_app; app = create_app('.'); uvicorn.run(app, host='0.0.0.0', port=5002)"
pause
