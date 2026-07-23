# Phase 0: Commercial Delivery and Exact Profile Gate - Research

**Researched:** 2026-07-23
**Scope:** Planning research for the commercial delivery skeleton, exact WeChat profile gate, local worker lifecycle, minimal key/read smoke, and minimal text-send smoke.
**Confidence:** HIGH for local toolchain/profile facts, HIGH for fail-closed gate shape, MEDIUM for packaged worker signing, LOW for Developer ID notarization until a valid signing identity exists.

## Executive Summary

Phase 0 should prove a narrow native macOS delivery path before the product invests further in analysis UI or batch sending. The current local toolchain supports a Swift 6 arm64 app skeleton and a Python 3.9.6 + Frida 16.7.19 worker. `codesign`, `notarytool`, and `stapler` are available through Command Line Tools, but `security find-identity -v -p codesigning` reports `0 valid identities found`, so Developer ID signing/notarization cannot be completed on this machine until the developer certificate is installed.

The phase should therefore produce two classes of evidence:

1. **Local executable gate evidence** that can be verified now: Swift app/helper builds, exact WeChat version/hash probe, worker attach/load/unload/detach lifecycle, helper cleanup checks, Chatlog key/read smoke command wiring, and minimal text-send smoke harness structure.
2. **Commercial package gate evidence** that is explicit and fail-closed: ad-hoc/local signed artifact can be built now; Developer ID signing, notary submission, stapling, and clean-Mac install are terminal checks that must report missing identity when unavailable rather than pretending to pass.

Phase 0 should not introduce the final lead-analysis data model, DeepSeek flow, dashboard, Excel export, video/file adapters, or batch sender. It should create the product skeleton and hard gates those later phases will reuse.

## Local Facts Verified This Turn

- `swift --version` returns Apple Swift `6.0.3`, target `arm64-apple-macosx15.0`.
- `python3 --version` returns `Python 3.9.6`.
- `python3` imports `frida` version `16.7.19`.
- `xcrun --find codesign` resolves to `/usr/bin/codesign`.
- `xcrun --find notarytool` resolves to `/Library/Developer/CommandLineTools/usr/bin/notarytool`.
- `xcrun --find stapler` resolves to `/Library/Developer/CommandLineTools/usr/bin/stapler`.
- `security find-identity -v -p codesigning` reports `0 valid identities found`.
- `go` is not currently available on PATH and was not found at `/opt/homebrew/bin/go` or `/usr/local/go/bin/go`.
- The installed Chatlog Alpha binary runs and documents `key`, `http`, and `action` commands.
- No running WeChat main process was visible in the last `ps` probe; `/Applications/WeChat.app/Contents/MacOS/WeChat` exists.
- The Chatlog source snapshot remains available at `/tmp/chatlog-alpha-spike.WWc9fK/repo` commit `2f54920d4aa78e1812819f77bb59a5e380c6f0ec`.
- The wechat-chatter source snapshot remains available at `/tmp/wechat-chatter-spike` commit `49114827bc83f8381eb638e8a56f3f0305fc1a1c`.

## Planning Implications

### Project Skeleton

Use a Swift Package/Application skeleton for Phase 0. Because Go is not installed locally, Phase 0 should not depend on a Go build step. The product can still adopt a Go core in a later phase if the toolchain is installed, but the first feasibility gate should use verified tools only.

Recommended Phase 0 structure:

- `Sources/WeChatSalesAgentApp/` for the native Swift entry point and basic diagnostics window.
- `Sources/AgentCore/` for profile gate, diagnostic models, process probing, command execution, and package gate orchestration.
- `native-worker/` for the minimal Python worker scripts and GumJS probe assets.
- `scripts/` for deterministic local verification commands.
- `dist/` for generated artifacts, ignored by git.

### Packaging Gate

Phase 0 should support three explicit package states:

- `local_unsigned`: build exists but has not been signed.
- `ad_hoc_signed`: local `codesign -s -` succeeded for development verification only.
- `developer_id_required`: no valid Developer ID Application identity exists, so notarization is blocked.

Do not label an ad-hoc artifact as commercial-ready. The UI/CLI diagnostic must say exactly which package gate is missing.

### Exact Profile Gate

The profile gate must validate the running process, not just the app bundle on disk. It must collect:

- process path
- CPU architecture
- WeChat version `4.1.11.55`
- build `269111`
- full `wechat.dylib` SHA-256 `c2a4794b343625a8013752095e76bc688acd42d48f30001a255620db2fc542a9`
- arm64 slice SHA-256 `da53625065d283d748f959627f5e4d724eb786f2911f49c91a72cc12f17d30f7`

Any mismatch must stop key extraction and sending before worker attachment.

### Worker Lifecycle Gate

The worker contract should stay narrow:

- `profile-probe`
- `attach-smoke`
- `key-smoke`
- `read-smoke`
- `text-send-smoke`
- `cleanup-smoke`

Each command should emit JSON Lines with a `status`, `step`, `code`, `message`, and optional evidence fields. Terminal states must be `passed`, `failed`, or `blocked`; there should be no silent fallback or retry substitution.

### Key/Read Smoke

For Phase 0, use the installed Chatlog Alpha binary as a smoke dependency because its key and HTTP commands are already verified locally. This is not the final data layer. The phase should wrap it as an external diagnostic with clear output parsing and terminal errors.

Minimum checks:

- `chatlog-darwin-arm64 key --help` is callable.
- `chatlog-darwin-arm64 http list` or documented HTTP call path is callable when a Chatlog service exists.
- If the service is not running or no account is logged in, the diagnostic reports the exact missing precondition.

### Text Send Smoke

Use the Chatlog upstream native text sender source as the reference implementation for Phase 0's minimal send smoke. The phase should not certify image, video, or file.

Relevant reference files:

- `/tmp/chatlog-alpha-spike.WWc9fK/repo/internal/wechat/send/assets/native_send_once.py`
- `/tmp/chatlog-alpha-spike.WWc9fK/repo/internal/wechat/send/assets/native/single_send_agent.js`
- `/tmp/chatlog-alpha-spike.WWc9fK/repo/internal/wechat/send/runner_darwin.go`
- `/tmp/chatlog-alpha-spike.WWc9fK/repo/internal/wechat/send/model.go`

The smoke test should target `filehelper` until a real customer confirmation gate exists. A successful result requires receiver-visible delivery, typed Ack evidence, unload/detach, no residual Frida helper, and WeChat health check.

## Risks and Required Plan Coverage

### Missing Developer ID Identity

The plan must include a task that detects `0 valid identities found` and records the package gate as blocked for Developer ID notarization. It may produce an ad-hoc signed local artifact but must not claim notarized commercial readiness without a valid certificate and notary credentials.

### Go Toolchain Drift

Project-level research recommended Go, but current PATH has no `go`. The Phase 0 plan must not require Go. If later phases still choose Go, they need a separate toolchain installation or vendored runtime decision.

### WeChat Not Running

Current `ps` did not show the WeChat main process. The profile gate and worker lifecycle commands must handle this as `WECHAT_NOT_RUNNING`, not as an ambiguous worker failure.

### Existing Invalidated File Path

The invalidated `uploadappattach -> sendappmsg` path must not be included in any Phase 0 task. File/video adapter research belongs to Phase 5.

## Validation Architecture

Phase 0 should be verified with a local validation manifest, for example `artifacts/phase0/validation.jsonl` or `dist/phase0-validation.jsonl`, generated by a single script command.

Required validation dimensions:

1. **Build:** Swift package/app builds for arm64 and produces the expected executable/app bundle.
2. **Package identity:** local signing state is detected; Developer ID identity absence is reported as a terminal missing credential.
3. **Exact profile:** matching WeChat profile passes only when version/build/full hash/slice hash all match; no running process or mismatch fails closed.
4. **Worker lifecycle:** Python/Frida worker can report version, attach/load/unload/detach on a permitted running target, and cleanup leaves no matching helper.
5. **Key/read smoke:** Chatlog smoke commands are callable and classify missing service/account/key states explicitly.
6. **Text send smoke:** minimal filehelper text smoke is present as an explicit, opt-in verification command and records receiver-visible/Ack/cleanup evidence when run.
7. **No fallback scan:** repository contains no Phase 0 implementation path using Hermes, clipboard, key simulation, share sheet, or `uploadappattach` production send.

## Suggested Plan Breakdown

1. Create Swift package/app skeleton, diagnostics models, and scripts.
2. Implement exact profile gate and hash probe with fixtures/tests.
3. Implement package/signing diagnostics and ad-hoc build script with Developer ID missing state.
4. Implement Python worker command contract for version/profile/attach lifecycle smoke.
5. Wrap Chatlog key/read smoke diagnostics.
6. Add text-send smoke harness from the validated upstream text sender reference, gated to exact profile and `filehelper`.
7. Add Phase 0 validation manifest and update `Agent.md` with new verified paths and local toolchain facts.

## Non-Goals for Phase 0

- No lead table, dashboard, Excel export, DeepSeek integration, or business scoring.
- No image/video/file certification.
- No batch send plan or real customer send.
- No web server or browser UI.
- No unsupported platform or WeChat version compatibility branch.
- No fallback transport.

---

*Research completed: 2026-07-23*
