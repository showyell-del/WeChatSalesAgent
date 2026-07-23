#!/usr/bin/env bash
set -euo pipefail

json_event() {
  local step="$1"
  local status="$2"
  local code="$3"
  local message="$4"
  printf '{"step":"%s","status":"%s","code":"%s","message":"%s","evidence":{}}\n' "$step" "$status" "$code" "$message"
}

no_fallback_scan() {
  local matches
  matches="$(rg -n "Hermes|clipboard|key simulation|share sheet|uploadappattach|sendappmsg" app native-worker scripts -g '!scripts/phase0_validate.sh' 2>/dev/null || true)"
  if [[ -n "$matches" ]]; then
    printf '%s\n' "$matches" >&2
    json_event "no_fallback_scan" "failed" "FORBIDDEN_PRODUCTION_PATH_FOUND" "Forbidden production transport string was found."
    return 1
  fi
  json_event "no_fallback_scan" "passed" "NO_FALLBACK_PATHS_FOUND" "No forbidden production transport strings found."
}

run_package() {
  scripts/build_phase0_app.sh
}

run_worker() {
  scripts/phase0_worker.sh version
  scripts/phase0_worker.sh probe-process
  scripts/phase0_worker.sh profile-gate
  scripts/phase0_worker.sh attach-smoke
}

run_chatlog() {
  scripts/phase0_chatlog_smoke.sh --help-smoke
  scripts/phase0_chatlog_smoke.sh --http-list-smoke
}

run_send_manifest() {
  scripts/phase0_worker.sh text-send-smoke-manifest
}

case "${1:-}" in
  --quick)
    scripts/build_phase0_app.sh
    no_fallback_scan
    json_event "phase0_quick" "passed" "PHASE0_QUICK_PASSED" "Quick Phase 0 validation passed."
    ;;
  --full)
    run_package
    run_worker
    run_chatlog
    run_send_manifest
    no_fallback_scan
    json_event "phase0_full" "passed" "PHASE0_FULL_PASSED" "Full Phase 0 validation passed with explicit blocked gates allowed."
    ;;
  --package)
    run_package
    ;;
  --worker)
    run_worker
    ;;
  --chatlog)
    run_chatlog
    ;;
  --send-smoke-manifest)
    run_send_manifest
    ;;
  --no-fallback-scan)
    no_fallback_scan
    ;;
  *)
    echo "Usage: $0 --quick|--full|--package|--worker|--chatlog|--send-smoke-manifest|--no-fallback-scan" >&2
    exit 2
    ;;
esac
