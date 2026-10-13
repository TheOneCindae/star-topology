#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export STAR_TOPOLOGY_TCP_HOST="${STAR_TOPOLOGY_TCP_HOST:-0.0.0.0}"
export STAR_TOPOLOGY_TCP_PORT="${STAR_TOPOLOGY_TCP_PORT:-5000}"
export STAR_TOPOLOGY_DB_PATH="${STAR_TOPOLOGY_DB_PATH:-data/star_topology.sqlite3}"
exec .venv/bin/uvicorn server.main:create_app --factory --host 0.0.0.0 --port "${HTTP_PORT:-8080}"
