@echo off
rem Build SchemaDocumenter.exe on Windows. Requires Python 3.10+ on PATH.
cd /d "%~dp0"
if not exist .venv python -m venv .venv || goto :error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements-dev.txt || goto :error
pyinstaller schemadoc.spec --noconfirm --clean || goto :error
echo.
echo Done. Your executable is dist\SchemaDocumenter.exe
goto :eof
:error
echo Build failed.
exit /b 1
