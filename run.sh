#!/usr/bin/env bash
set -euo pipefail
ROOT="$(dirname "$(readlink -f "$0")")"
exec python3 -m uvicorn server:app --app-dir "$ROOT" --host "${HOST:-0.0.0.0}" --port "${PORT:-8020}" --workers 1 --limit-concurrency 16 --timeout-keep-alive 5
