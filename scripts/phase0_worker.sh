#!/usr/bin/env bash
set -euo pipefail

python3 native-worker/phase0_worker.py "$@"
