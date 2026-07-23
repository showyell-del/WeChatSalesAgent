#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

/usr/bin/python3 -m unittest discover -s Tests -p 'test_phase4_*.py' -v
/usr/bin/python3 -m py_compile agent_core/workspace_service.py agent_core/workspace_cli.py

VERIFY_DIR="$(mktemp -d /tmp/wechat-sales-phase4.XXXXXX)"
trap 'rm -rf "$VERIFY_DIR"' EXIT
/usr/bin/python3 -c 'import json,sys; from Tests.test_phase4_workspace import create_fixture; from agent_core.workspace_service import load_snapshot; create_fixture(sys.argv[1]); open(sys.argv[2],"w",encoding="utf-8").write(json.dumps(load_snapshot(sys.argv[1],"account_1"),ensure_ascii=False))' "$VERIFY_DIR/fixture.sqlite3" "$VERIFY_DIR/snapshot.json"

scripts/build_phase0_app.sh > "$VERIFY_DIR/build.log"
dist/phase0/WeChatSalesAgent.app/Contents/MacOS/WeChatSalesAgent --snapshot "$VERIFY_DIR/snapshot.json" --ui-smoke
dist/phase0/WeChatSalesAgent.app/Contents/MacOS/WeChatSalesAgent --snapshot "$VERIFY_DIR/snapshot.json" --render-preview "$VERIFY_DIR/native-workspace.png"
test -s "$VERIFY_DIR/native-workspace.png"

ln -s /Users/gongshaoyou/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules "$VERIFY_DIR/node_modules"
cp scripts/build_lead_workbook.mjs "$VERIFY_DIR/build_lead_workbook.mjs"
(
  cd "$VERIFY_DIR"
  PHASE4_VERIFY_DIR="$VERIFY_DIR/workbook-previews" /Users/gongshaoyou/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node \
    "$VERIFY_DIR/build_lead_workbook.mjs" "$VERIFY_DIR/snapshot.json" "$VERIFY_DIR/客户激活表.xlsx"
)
test -s "$VERIFY_DIR/客户激活表.xlsx"
test -s "$VERIFY_DIR/workbook-previews/dashboard.png"
test -s "$VERIFY_DIR/workbook-previews/leads.png"
/usr/bin/unzip -l "$VERIFY_DIR/客户激活表.xlsx" | rg -q 'xl/workbook.xml'
rg -q '"高意向",1,0\.5' "$VERIFY_DIR/workbook-previews/inspect.ndjson"
WECHAT_SALES_AGENT_DB="$VERIFY_DIR/fixture.sqlite3" scripts/phase4_export.sh "$VERIFY_DIR/end-to-end.xlsx" account_1
test -s "$VERIFY_DIR/end-to-end.xlsx"
! rg -n 'WKWebView|WebView|http://127\.0\.0\.1|localhost:' app agent_core

set +e
CURRENT_OUTPUT="$(scripts/phase4_workspace.sh --db runtime/agent_state.sqlite3 snapshot --account-id wxid_3prysbeqgvci22_9f8d 2>&1)"
CURRENT_CODE=$?
set -e
test "$CURRENT_CODE" -eq 1
printf '%s' "$CURRENT_OUTPUT" | rg -q 'PUBLISHED_ANALYSIS_MISSING'

printf '%s\n' '{"step":"phase4_local","status":"passed","code":"PHASE4_LOCAL_VALIDATION_OK","message":"Native AppKit dashboard, lead evidence workspace, and real XLSX export passed local validation.","evidence":{}}'
