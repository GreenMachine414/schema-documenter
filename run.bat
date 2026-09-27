@echo off
rem Run from source without building. Pass arguments to use the command line.
cd /d "%~dp0"
if not exist .venv (python -m venv .venv && .venv\Scripts\pip install -r requirements.txt)
.venv\Scripts\python launcher.py %*
