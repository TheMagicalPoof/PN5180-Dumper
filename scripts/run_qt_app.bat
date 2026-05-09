@echo off
setlocal
cd /d "%~dp0"
cd ..

set PYTHONPATH=host\python
python -m pn5180_dumper.qt_app
