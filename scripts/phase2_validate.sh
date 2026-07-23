#!/usr/bin/env bash
set -euo pipefail

account_id="${1:-wxid_3prysbeqgvci22_9f8d}"

python3 -m unittest discover -s Tests -p 'test_*.py' -v
python3 -m compileall -q agent_core
python3 -m agent_core.corpus_validate --account-id "$account_id"
