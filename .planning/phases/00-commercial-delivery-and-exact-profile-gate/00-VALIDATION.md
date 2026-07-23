---
phase: 00
slug: commercial-delivery-and-exact-profile-gate
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-23
---

# Phase 00 - Validation Strategy

Per-phase validation contract for the commercial delivery and exact profile gate.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Swift Package tests, shell verification scripts, Python worker smoke commands |
| **Config file** | `Package.swift`, `scripts/phase0_validate.sh` |
| **Quick run command** | `swift test && scripts/phase0_validate.sh --quick` |
| **Full suite command** | `swift test && scripts/phase0_validate.sh --full` |
| **Estimated runtime** | ~60 seconds without live WeChat smoke; manual smoke depends on WeChat login and filehelper delivery |

## Sampling Rate

- **After every task commit:** Run `swift test && scripts/phase0_validate.sh --quick`
- **After every plan wave:** Run `swift test && scripts/phase0_validate.sh --full`
- **Before verification:** Full suite must pass, except Developer ID and live WeChat smoke may report explicit blocked/manual states.
- **Max feedback latency:** 90 seconds for automated checks.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 00-01-01 | 01 | 1 | Platform boundary | T-00-01 | Native app skeleton builds without Web UI | build/unit | `swift test` | W0 | pending |
| 00-01-02 | 01 | 1 | Exact profile gate | T-00-02 | Mismatch and no-process states fail closed before key/send | unit/script | `scripts/phase0_validate.sh --quick` | W0 | pending |
| 00-02-01 | 02 | 1 | Commercial feasibility gate | T-00-03 | Missing Developer ID is terminal, not treated as pass | script | `scripts/phase0_validate.sh --package` | W0 | pending |
| 00-03-01 | 03 | 2 | Worker lifecycle | T-00-04 | Worker emits explicit JSON states and detaches cleanly | python/script | `scripts/phase0_validate.sh --worker` | W0 | pending |
| 00-04-01 | 04 | 2 | Key/read smoke | T-00-05 | Chatlog missing-service/account/key states are classified explicitly | script | `scripts/phase0_validate.sh --chatlog` | W0 | pending |
| 00-05-01 | 05 | 3 | Minimal send smoke | T-00-06 | Text send smoke is exact-profile gated and opt-in to filehelper | manual+script | `scripts/phase0_validate.sh --send-smoke-manifest` | W0 | pending |
| 00-06-01 | 06 | 3 | No fallback mechanisms | T-00-07 | Repository scan rejects forbidden transport strings | script | `scripts/phase0_validate.sh --no-fallback-scan` | W0 | pending |

## Wave 0 Requirements

- [ ] `Package.swift` - Swift package test target exists.
- [ ] `scripts/phase0_validate.sh` - deterministic validator exists and supports `--quick`, `--full`, `--package`, `--worker`, `--chatlog`, `--send-smoke-manifest`, and `--no-fallback-scan`.
- [ ] `native-worker/phase0_worker.py` - worker command entrypoint exists.
- [ ] `Tests/AgentCoreTests/` - unit tests cover profile gate, diagnostics, and package gate states.

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Developer ID notarized install on clean Mac | Commercial feasibility gate | No valid Developer ID identity is currently installed locally | Install Developer ID Application certificate and notary credentials, run full package command, submit with `notarytool`, staple, then install on clean Apple Silicon Mac. |
| Receiver-visible filehelper text send | Minimal native send smoke | Requires logged-in WeChat, exact profile, and visible receiver check | Start WeChat 4.1.11.55, run the opt-in text smoke command targeting `filehelper`, confirm typed Ack, visible message, cleanup, and no residual helper. |
| Key acquisition with logged-in account | Key/read smoke | Requires logged-in WeChat account and local security posture | Run Chatlog key smoke after WeChat login and confirm explicit success or exact failure step. |

## Validation Sign-Off

- [x] All planned tasks must have automated verify commands or explicit manual-only reasons.
- [x] Sampling continuity prevents three consecutive implementation tasks without automated verify.
- [x] Wave 0 defines missing validation infrastructure.
- [x] No watch-mode flags.
- [x] Feedback latency target is below 90 seconds for automated checks.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** pending
