@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist "ComfyUI\.venv-rocm\Scripts\python.exe" (
  echo GPU Python environment is missing. See docs.
  pause
  exit /b 1
)
"ComfyUI\.venv-rocm\Scripts\python.exe" services\studio\launch.py
if errorlevel 1 pause
