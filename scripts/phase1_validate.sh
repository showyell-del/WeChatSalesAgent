#!/usr/bin/env bash
set -euo pipefail

account_id="${1:-wxid_3prysbeqgvci22_9f8d}"

python3 -m unittest discover -s Tests -p 'test_*.py' -v
python3 -m compileall -q agent_core
scripts/phase1_sync.sh health
scripts/phase1_sync.sh accounts
scripts/phase1_sync.sh switch --account-id "$account_id"
scripts/phase1_sync.sh connect --account-id "$account_id"
scripts/phase1_sync.sh sync --account-id "$account_id" --limit 5000
scripts/phase1_sync.sh status
