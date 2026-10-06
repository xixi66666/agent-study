@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set "VIDEO_RUN_ID=%~1"
if not defined VIDEO_RUN_ID (
  for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "VIDEO_RUN_ID=%%I_cat_comic"
)
"ComfyUI\.venv-rocm\Scripts\python.exe" -u services\media\produce_video.py --config config\cat_comic_video.json --storyboard prompts\stories\cat_biscuit_mystery.json --run-id "%VIDEO_RUN_ID%"
if errorlevel 1 goto failed
"ComfyUI\.venv-rocm\Scripts\python.exe" -u services\media\add_dialogue.py --run-dir "runs\%VIDEO_RUN_ID%"
if errorlevel 1 goto failed
echo Completed. See runs\%VIDEO_RUN_ID%\final\film_with_dialogue.mp4
pause
exit /b 0
:failed
echo Generation failed. Check this batch's logs and the ComfyUI console.
pause
exit /b 1
