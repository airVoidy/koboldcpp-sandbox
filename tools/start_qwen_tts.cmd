@echo off
title Qwen TTS (All-in-One)
echo ============================================
echo  Qwen TTS - CustomVoice + VoiceDesign + Proxy
echo ============================================
echo.

set CONDA_ENV=tts
set DTYPE=bfloat16
set DEVICE=cuda:0

echo [1/3] Starting CustomVoice on :8000 ...
start "Qwen CustomVoice :8000" wsl bash -lc "source /home/vairy/miniconda3/etc/profile.d/conda.sh && conda activate %CONDA_ENV% && python -m qwen_tts.cli.demo Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice --dtype %DTYPE% --no-flash-attn --device %DEVICE% --port 8000"

timeout /t 5 /nobreak >nul

echo [2/3] Starting VoiceDesign on :8001 ...
start "Qwen VoiceDesign :8001" wsl bash -lc "source /home/vairy/miniconda3/etc/profile.d/conda.sh && conda activate %CONDA_ENV% && python -m qwen_tts.cli.demo Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign --dtype %DTYPE% --no-flash-attn --device %DEVICE% --port 8001"

echo Waiting for models to load ...
timeout /t 30 /nobreak >nul

echo [3/3] Starting TTS Proxy on :8100 ...
echo.
echo ============================================
echo  CustomVoice:  http://localhost:8000
echo  VoiceDesign:  http://localhost:8001
echo  TTS Proxy:    http://localhost:8100
echo ============================================
echo.

wsl bash -lc "source /home/vairy/miniconda3/etc/profile.d/conda.sh && conda activate %CONDA_ENV% && python /mnt/c/llm/KoboldCPP\ agentic\ sandbox/tools/qwen_tts_server.py --port 8100"
pause
