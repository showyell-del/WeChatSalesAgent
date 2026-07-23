---
phase: 00
plan: 01
subsystem: native-app-skeleton
tags: [appkit, packaging, phase0]
key-files:
  - app/Phase0App/main.m
  - app/Phase0App/Info.plist
  - scripts/build_phase0_app.sh
---

# Plan 00-01 Summary

## What Changed

- Created a native Objective-C/AppKit app skeleton in `app/Phase0App/`.
- Added bundle metadata with `LSMinimumSystemVersion` set to `15.0`.
- Added an app smoke mode that emits `PHASE0_APP_LAUNCHED` as JSON and exits.
- Built the app through `scripts/build_phase0_app.sh` using `/usr/bin/clang`.

## Verification

- `scripts/build_phase0_app.sh` exits 0.
- `dist/phase0/WeChatSalesAgent.app/Contents/MacOS/WeChatSalesAgent --smoke` emits `PHASE0_APP_LAUNCHED`.

## Deviations

- Planned Swift package implementation was replaced with Objective-C/AppKit because local Swift/SDK tooling is currently inconsistent. This preserves the native macOS Phase 0 goal and removes the unusable Swift path.

## Self-Check

PASSED
