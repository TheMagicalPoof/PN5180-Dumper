@echo off
setlocal
cd /d "%~dp0"
cd ..

echo Starting dump capture...
python capture_dump.py --auto-port --once

echo.
if errorlevel 1 (
  echo Capture finished with errors.
) else (
  echo Capture finished successfully.
)

pause
