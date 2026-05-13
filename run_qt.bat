@echo off
cd /d "%~dp0"
python app_qt.py
if errorlevel 1 pause
