@echo off
title Qwen TTS Proxy
echo Qwen TTS Proxy Server (lightweight, no torch)
echo Expects Gradio demos: CustomVoice :8000, VoiceDesign :8001
echo.
wsl -e /usr/bin/python3 "/mnt/c/llm/KoboldCPP agentic sandbox/tools/qwen_tts_server.py" --port 8100
pause
