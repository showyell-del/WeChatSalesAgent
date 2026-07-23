#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  printf '%s\n' 'usage: scripts/phase4_export.sh OUTPUT.xlsx [ACCOUNT_ID]'
  exit 2
fi

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
case "$1" in
  /*) OUTPUT_PATH="$1" ;;
  *) OUTPUT_PATH="$PROJECT_DIR/$1" ;;
esac
ACCOUNT_ID="${2:-}"
STATE_DB="${WECHAT_SALES_AGENT_DB:-$PROJECT_DIR/runtime/agent_state.sqlite3}"
NODE_BIN="/Users/gongshaoyou/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
NODE_MODULES_SOURCE="/Users/gongshaoyou/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules"
WORK_DIR="$(mktemp -d /tmp/wechat-sales-export.XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT
ln -s "$NODE_MODULES_SOURCE" "$WORK_DIR/node_modules"
cp "$PROJECT_DIR/scripts/build_lead_workbook.mjs" "$WORK_DIR/build_lead_workbook.mjs"
if [[ -n "$ACCOUNT_ID" ]]; then
  "$PROJECT_DIR/scripts/phase4_workspace.sh" --db "$STATE_DB" snapshot --account-id "$ACCOUNT_ID" > "$WORK_DIR/snapshot.json"
else
  "$PROJECT_DIR/scripts/phase4_workspace.sh" --db "$STATE_DB" snapshot > "$WORK_DIR/snapshot.json"
fi
cd "$WORK_DIR"
exec "$NODE_BIN" "$WORK_DIR/build_lead_workbook.mjs" "$WORK_DIR/snapshot.json" "$OUTPUT_PATH"
