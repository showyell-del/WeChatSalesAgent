---
phase: 00
plan: 04
subsystem: package-validation
tags: [codesign, validation, agent-notes, phase0]
key-files:
  - scripts/build_phase0_app.sh
  - scripts/phase0_validate.sh
  - Agent.md
---

# Plan 00-04 Summary

## What Changed

- Added local AppKit app build and ad-hoc signing script.
- Added unified Phase 0 validation script with package, worker, Chatlog, send-manifest, and no-fallback checks.
- Verified Developer ID identity absence is reported as `DEVELOPER_ID_IDENTITY_MISSING`.
- Updated `Agent.md` with Phase 0 local delivery facts and Swift toolchain caveat.

## Verification

- `scripts/phase0_validate.sh --quick` exits 0.
- `scripts/phase0_validate.sh --full` exits 0.
- `dist/phase0/WeChatSalesAgent.app/Contents/MacOS/WeChatSalesAgent --smoke` emits `PHASE0_APP_LAUNCHED`.
- Full validation reports `NO_FALLBACK_PATHS_FOUND`.

## Deviations

- Developer ID notarization and clean-Mac install remain blocked/manual because no valid Developer ID signing identity is installed locally.

## Self-Check

PASSED
