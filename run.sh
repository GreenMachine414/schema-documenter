#!/usr/bin/env bash
# Run from source without building. Pass arguments to use the command line.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  ${PYTHON:-python3} -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
exec .venv/bin/python launcher.py "$@"
