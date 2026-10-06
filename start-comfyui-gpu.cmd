@echo off
setlocal
cd /d "%~dp0ComfyUI"
".venv-rocm\Scripts\python.exe" main.py --listen 127.0.0.1 --port 8189 --reserve-vram 3 --database-url sqlite:///user/comfyui-gpu.db --auto-launch
pause
