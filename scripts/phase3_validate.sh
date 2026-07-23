#!/usr/bin/env bash
set -euo pipefail

account_id="${1:-wxid_3prysbeqgvci22_9f8d}"

python3 -m unittest discover -s Tests -p 'test_*.py' -v
python3 -m compileall -q agent_core
scripts/phase3_ai.sh status
scripts/phase3_ai.sh estimate --account-id "$account_id"

matches="$(rg -n 'json_repair|langchain|instructor|tenacity|backoff' agent_core requirements.txt 2>/dev/null || true)"
if [[ -n "$matches" ]]; then
  printf '%s\n' "$matches" >&2
  exit 1
fi

printf '%s\n' '{"step":"phase3_local","status":"passed","code":"PHASE3_LOCAL_VALIDATION_OK","message":"Strict DeepSeek client, validation, candidate selection, and cost ledger passed local validation.","evidence":{}}'
