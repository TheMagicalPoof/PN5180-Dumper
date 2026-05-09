@echo off
setlocal
cd /d "%~dp0"
cd ..

echo Starting dump capture...
set PYTHONPATH=host\python
python -m pn5180_dumper.cli capture --auto-port --once

echo.
if errorlevel 1 (
  echo Capture finished with errors.
) else (
  echo Capture finished successfully.
)

pause
