---
phase: 00
status: human_needed
verified_at: 2026-07-23
---

# Phase 00 Verification

## Automated Evidence

| Gate | Evidence | Result |
|------|----------|--------|
| Native app build | `scripts/build_phase0_app.sh` | PASSED |
| App smoke | `dist/phase0/WeChatSalesAgent.app/Contents/MacOS/WeChatSalesAgent --smoke` | PASSED |
| Worker version | `python3 native-worker/phase0_worker.py version` | PASSED, Frida 16.7.19 |
| Profile gate | `python3 native-worker/phase0_worker.py profile-gate` | BLOCKED as `WECHAT_NOT_RUNNING` |
| Worker lifecycle | `scripts/phase0_validate.sh --worker` | PASSED with explicit blocked no-WeChat states |
| Chatlog smoke | `scripts/phase0_validate.sh --chatlog` | PASSED |
| Send smoke manifest | `scripts/phase0_validate.sh --send-smoke-manifest` | BLOCKED as `TEXT_SEND_SMOKE_MANUAL_REQUIRED` |
| No fallback scan | `scripts/phase0_validate.sh --no-fallback-scan` | PASSED |
| Full validation | `scripts/phase0_validate.sh --full` | PASSED with documented blocked gates |

## Human Verification Needed

1. Developer ID notarized/stapled clean-Mac install cannot pass until a valid Developer ID Application identity and notary credentials are installed.
2. Live WeChat attach/profile/typed Ack text send smoke cannot pass while WeChat is not running and visible filehelper delivery has not been confirmed.

## Status

`human_needed` — Phase 0 local automated gates are implemented and passing. Commercial notarization and live text-send smoke remain explicit manual/external gates; they are not treated as completed.
