@echo off
rem Build dist\SchemaDocumenter.exe on Windows. Requires Python 3.10+ on PATH.
rem Other systems: see "Building locally" in README.md.
cd /d "%~dp0"
if not exist .venv python -m venv .venv || goto :error
call .venv\Scripts\activate.bat
pip install -e ".[dev]" || goto :error
pyinstaller schemadoc.spec --noconfirm --clean || goto :error
echo.
echo Done. Your executable is dist\SchemaDocumenter.exe
goto :eof
:error
echo Build failed.
exit /b 1
