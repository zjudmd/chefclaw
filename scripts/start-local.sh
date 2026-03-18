#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/python ]; then
  echo "Missing .venv. Run: python3 -m venv .venv && . .venv/bin/activate && pip install -e .[dev]" >&2
  exit 1
fi

. .venv/bin/activate
exec chef-claw
