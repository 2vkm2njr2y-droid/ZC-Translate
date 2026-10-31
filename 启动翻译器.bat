@echo off
cd /d "%~dp0"
if exist "%~dp0dist\ZCTranslate\ZCTranslate.exe" (
  set "ZC_MODELS_DIR=%~dp0models"
  start "" "%~dp0dist\ZCTranslate\ZCTranslate.exe"
  exit /b 0
)
if not exist ".venv-runtime\Scripts\pythonw.exe" (
  echo First run: preparing the Python environment...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_env.ps1"
  if errorlevel 1 (
    echo Environment setup failed. See the messages above.
    pause
    exit /b 1
  )
)
start "" ".venv-runtime\Scripts\pythonw.exe" "%~dp0app\desktop.py"
