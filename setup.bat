@echo off
rem ============================================================
rem  JASEM setup: virtual environment + dependencies + models
rem ============================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] creating virtual environment...
  python -m venv .venv
  if errorlevel 1 ( echo venv creation failed & pause & exit /b 1 )
)

echo [2/3] installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo dependency installation failed & pause & exit /b 1 )

echo [3/3] downloading speech models (first time only)...
set PYTHONPATH=%~dp0src
".venv\Scripts\python.exe" scripts\download_models.py
if errorlevel 1 ( echo model download failed & pause & exit /b 1 )

echo.
echo Setup complete. Run run.bat to start JASEM.
pause
