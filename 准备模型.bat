@echo off
cd /d "%~dp0"
if not exist ".venv-convert\Scripts\python.exe" (
  echo First run: preparing the model conversion environment...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_env.ps1"
  if errorlevel 1 (
    echo Environment setup failed.
    pause
    exit /b 1
  )
)
echo Preparing Hy-MT2-1.8B ^(download about 4 GB, then convert^)...
".venv-convert\Scripts\python.exe" "%~dp0scripts\prepare_model.py" --profile balanced %*
set CODE=%ERRORLEVEL%
echo.
if %CODE%==0 (
  echo Model preparation complete. You can now double-click the launcher.
) else (
  echo Model preparation failed with code %CODE%. See the log above.
)
pause
exit /b %CODE%
