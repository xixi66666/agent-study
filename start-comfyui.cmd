@echo off
setlocal
cd /d "%~dp0ComfyUI"
".venv\Scripts\python.exe" main.py --cpu --listen 127.0.0.1 --port 8188 --auto-launch
pause
