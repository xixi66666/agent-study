@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if "%~1"=="" (
  "ComfyUI\.venv-rocm\Scripts\python.exe" -u services\media\produce_video.py --storyboard prompts\stories\red_panda_morning.json
) else (
  "ComfyUI\.venv-rocm\Scripts\python.exe" -u services\media\produce_video.py %*
)
if errorlevel 1 (
  echo Generation failed. Check the run logs and ComfyUI console.
  pause
  exit /b 1
)
pause
