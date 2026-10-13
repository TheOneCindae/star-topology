#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python -m client.main --id "$1" --host "$2" --port "${3:-5000}"
