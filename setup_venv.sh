#!/usr/bin/env bash
set -euo pipefail

# Create and activate venv
python -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate

# Upgrade pip and install requirements
python -m pip install --upgrade pip setuptools wheel
pip install --upgrade pip
pip install -r requirements.txt

# If playwright is in requirements, install browsers
if python -c "import importlib, sys; sys.exit(0) if importlib.util.find_spec('playwright') else sys.exit(1)"; then
  python -m playwright install
fi

echo "Virtualenv created in .venv. Activate with: source .venv/bin/activate"
