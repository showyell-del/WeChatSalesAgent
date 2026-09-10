#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

/usr/bin/python3 -m unittest discover -s Tests -p 'test_phase4_*.py' -v
/usr/bin/python3 -m py_compile agent_core/workspace_service.py agent_core/workspace_cli.py

VERIFY_DIR="$(mktemp -d /tmp/wechat-sales-phase4.XXXXXX)"
trap 'rm -rf "$VERIFY_DIR"' EXIT
NODE_SOURCE="${WECHAT_AGENT_NODE_SOURCE:?WECHAT_AGENT_NODE_SOURCE must point to the locked Node dependency root}"
/usr/bin/python3 -c 'import json,sys; from Tests.test_phase4_workspace import create_fixture; from agent_core.workspace_service import load_snapshot; create_fixture(sys.argv[1]); open(sys.argv[2],"w",encoding="utf-8").write(json.dumps(load_snapshot(sys.argv[1],"account_1"),ensure_ascii=False))' "$VERIFY_DIR/fixture.sqlite3" "$VERIFY_DIR/snapshot.json"

scripts/build_phase0_app.sh > "$VERIFY_DIR/build.log"
dist/WeChatSalesAgent.app/Contents/MacOS/WeChatSalesAgent --snapshot "$VERIFY_DIR/snapshot.json" --ui-smoke
dist/WeChatSalesAgent.app/Contents/MacOS/WeChatSalesAgent --snapshot "$VERIFY_DIR/snapshot.json" --render-preview "$VERIFY_DIR/native-workspace.png"
test -s "$VERIFY_DIR/native-workspace.png"

ln -s "$NODE_SOURCE/node_modules" "$VERIFY_DIR/node_modules"
cp scripts/build_lead_workbook.mjs "$VERIFY_DIR/build_lead_workbook.mjs"
(
  cd "$VERIFY_DIR"
  PHASE4_VERIFY_DIR="$VERIFY_DIR/workbook-previews" "$NODE_SOURCE/bin/node" \
    "$VERIFY_DIR/build_lead_workbook.mjs" "$VERIFY_DIR/snapshot.json" "$VERIFY_DIR/客户激活表.xlsx"
)
test -s "$VERIFY_DIR/客户激活表.xlsx"
test -s "$VERIFY_DIR/workbook-previews/dashboard.png"
test -s "$VERIFY_DIR/workbook-previews/leads.png"
/usr/bin/unzip -l "$VERIFY_DIR/客户激活表.xlsx" | rg -q 'xl/workbook.xml'
rg -q '"高意向",1,0\.5' "$VERIFY_DIR/workbook-previews/inspect.ndjson"
WECHAT_SALES_AGENT_DB="$VERIFY_DIR/fixture.sqlite3" scripts/phase4_export.sh "$VERIFY_DIR/end-to-end.xlsx" account_1
test -s "$VERIFY_DIR/end-to-end.xlsx"
rg -q 'agent_core.message_search_cli' app/Phase0App/main.m
rg -q '消息检索' app/Phase0App/main.m
! rg -n 'WKWebView|WebView|openURL:dashboardURL' app agent_core

/usr/bin/python3 -c 'import sqlite3,sys; from Tests.test_phase4_workspace import SCHEMA; c=sqlite3.connect(sys.argv[1]); c.executescript(SCHEMA); c.execute("INSERT INTO accounts VALUES(?,?,?,?)",("missing_account","/tmp/missing","verified",1)); c.execute("INSERT INTO app_state VALUES(?,?,?)",("active_account","missing_account",1)); c.execute("INSERT INTO generations VALUES(?,?,?,?)",("missing_generation","missing_account","published",1)); c.execute("INSERT INTO corpus_runs VALUES(?,?,?,?,?)",("missing_corpus","missing_generation","missing_account","published",1)); c.execute("INSERT INTO corpus_conversations VALUES(?,?)",("missing_corpus","eligible")); c.commit(); c.close()' "$VERIFY_DIR/missing.sqlite3"
set +e
MISSING_OUTPUT="$(scripts/phase4_workspace.sh --db "$VERIFY_DIR/missing.sqlite3" snapshot --account-id missing_account 2>&1)"
MISSING_CODE=$?
set -e
test "$MISSING_CODE" -eq 1
printf '%s' "$MISSING_OUTPUT" | rg -q 'PUBLISHED_ANALYSIS_MISSING'

printf '%s\n' '{"step":"phase4_local","status":"passed","code":"PHASE4_LOCAL_VALIDATION_OK","message":"Native AppKit dashboard, lead evidence workspace, and real XLSX export passed local validation.","evidence":{}}'
