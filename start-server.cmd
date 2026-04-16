@echo off
title Kobold Sandbox Server :5002
cd /d "%~dp0"
python -c "import sys; sys.path.insert(0,'src'); import uvicorn; from kobold_sandbox.server import create_app; app = create_app('.'); uvicorn.run(app, host='0.0.0.0', port=5002)"
pause
