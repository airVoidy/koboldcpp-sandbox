@echo off
cd /d "%~dp0\.."
python tools/fs_sync.py --root "C:\llm\KoboldCPP agentic sandbox\root" --interval 5 -v %*
