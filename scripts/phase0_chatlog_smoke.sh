#!/usr/bin/env bash
set -euo pipefail

CHATLOG_BIN="./chatlog_2f54920_darwin_arm64/chatlog-darwin-arm64"

json_event() {
  local step="$1"
  local status="$2"
  local code="$3"
  local message="$4"
  printf '{"step":"%s","status":"%s","code":"%s","message":"%s","evidence":{}}\n' "$step" "$status" "$code" "$message"
}

if [[ ! -x "$CHATLOG_BIN" ]]; then
  json_event "chatlog" "failed" "CHATLOG_BINARY_MISSING" "Chatlog Alpha binary is missing or not executable."
  exit 1
fi

case "${1:-}" in
  --help-smoke)
    "$CHATLOG_BIN" key --help >/dev/null
    "$CHATLOG_BIN" http --help >/dev/null
    json_event "chatlog_help" "passed" "CHATLOG_HELP_CALLABLE" "Chatlog key and http help commands are callable."
    ;;
  --http-list-smoke)
    if "$CHATLOG_BIN" http list >/dev/null 2>&1; then
      json_event "chatlog_http" "passed" "CHATLOG_HTTP_LIST_CALLABLE" "Chatlog HTTP endpoint list is callable."
    else
      json_event "chatlog_http" "blocked" "CHATLOG_SERVICE_UNAVAILABLE" "Chatlog HTTP service is not available."
    fi
    ;;
  *)
    echo "Usage: $0 --help-smoke|--http-list-smoke" >&2
    exit 2
    ;;
esac
