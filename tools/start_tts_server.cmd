@echo off
title Qwen TTS Server
cd /d "%~dp0"

echo === Qwen TTS Stack ===
echo.

REM Start CustomVoice on :8000
echo [1/3] Starting CustomVoice on :8000...
start "Qwen CustomVoice" wsl bash -c "source /home/vairy/miniforge/etc/profile.d/conda.sh && source /home/vairy/miniforge/etc/profile.d/mamba.sh && mamba activate airy_ml && python -m qwen_tts.cli.demo Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice --dtype bfloat16 --device cuda:0 --port 8000"

echo Waiting for CustomVoice to load...
timeout /t 30 /nobreak >nul

REM Start VoiceDesign on :8001
echo [2/3] Starting VoiceDesign on :8001...
start "Qwen VoiceDesign" wsl bash -c "source /home/vairy/miniforge/etc/profile.d/conda.sh && source /home/vairy/miniforge/etc/profile.d/mamba.sh && mamba activate airy_ml && python -m qwen_tts.cli.demo Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign --dtype bfloat16 --device cuda:0 --port 8001"

echo Waiting for VoiceDesign to load...
timeout /t 30 /nobreak >nul

REM Start proxy server on :8100
echo [3/3] Starting TTS Proxy on :8100...
wsl bash -c "source /home/vairy/miniforge/etc/profile.d/conda.sh && source /home/vairy/miniforge/etc/profile.d/mamba.sh && mamba activate airy_ml && python /mnt/c/llm/KoboldCPP\ agentic\ sandbox/tools/qwen_tts_server.py --port 8100 --custom-url http://localhost:8000 --design-url http://localhost:8001"

pause
