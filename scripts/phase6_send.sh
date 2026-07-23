#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec /usr/bin/python3 -m agent_core.send_cli "$@"
