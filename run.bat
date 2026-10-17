@echo off
rem ============================================================
rem  JASEM - one-command launcher
rem  Runs the assistant from the project virtual environment.
rem ============================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [JASEM] virtual environment missing. Run setup.bat first.
  pause
  exit /b 1
)

set PYTHONPATH=%~dp0src
".venv\Scripts\python.exe" -m jasem %*
if errorlevel 1 (
  echo.
  echo [JASEM] exited with an error. See logs in %APPDATA%\JASEM\logs
  pause
)
