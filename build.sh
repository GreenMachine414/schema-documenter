#!/usr/bin/env bash
# Build the executable on macOS or Linux. Requires Python 3.10+ (with Tk).
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
[ -d .venv ] || "$PY" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
pip install -r requirements-dev.txt
pyinstaller schemadoc.spec --noconfirm --clean
if [ -d dist/SchemaDocumenter.app ]; then
  echo "Done. Your app is dist/SchemaDocumenter.app"
else
  echo "Done. Your executable is dist/SchemaDocumenter"
fi
