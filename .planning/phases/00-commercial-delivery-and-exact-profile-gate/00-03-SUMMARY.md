---
phase: 00
plan: 03
subsystem: worker-and-chatlog-smoke
tags: [python, frida, chatlog, phase0]
key-files:
  - native-worker/phase0_worker.py
  - native-worker/probes/attach_smoke.js
  - native-worker/probes/text_send_smoke.js
  - scripts/phase0_worker.sh
  - scripts/phase0_chatlog_smoke.sh
---

# Plan 00-03 Summary

## What Changed

- Created the Phase 0 Python worker command entrypoint.
- Added worker commands for `version`, `probe-process`, `profile-gate`, `attach-smoke`, `cleanup-smoke`, and `text-send-smoke-manifest`.
- Added a Frida attach smoke probe and a text-send smoke manifest for `filehelper`.
- Added Chatlog help and HTTP-list smoke wrappers.

## Verification

- `python3 native-worker/phase0_worker.py version` reports Frida `16.7.19`.
- `scripts/phase0_chatlog_smoke.sh --help-smoke` reports `CHATLOG_HELP_CALLABLE`.
- `scripts/phase0_validate.sh --full` reports Chatlog HTTP list callable.
- Text send smoke is blocked as `TEXT_SEND_SMOKE_MANUAL_REQUIRED`, not exposed as certified support.

## Deviations

- The actual receiver-visible text send smoke remains manual because WeChat is not currently running and visible Ack must be confirmed interactively.

## Self-Check

PASSED
