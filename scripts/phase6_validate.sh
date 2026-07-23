#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
/usr/bin/python3 -m py_compile agent_core/send_store.py agent_core/send_cli.py agent_core/workspace_service.py Tests/test_phase6_send.py
/usr/bin/python3 -m unittest Tests.test_phase6_send
printf '%s\n' '{"step":"phase6_local","status":"passed","code":"PHASE6_SEND_LIFECYCLE_OK","message":"Audited send batch creation, attachment hashing, certification gating, cancellation, blocking dispatch, and workspace send status projection passed local validation.","evidence":{}}'
