#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 1 ]; then
  echo 'Usage: bash scripts/setup_env.sh <new-user-owned-venv-path>'
  exit 2
fi
if [ -e "$1" ]; then
  echo 'Refusing to replace an existing environment.'
  exit 2
fi
python3.12 -m venv "$1"
"$1/bin/python" -m pip install --index-url https://pypi.org/simple -r "$(dirname "$0")/../requirements.txt"
