# Final Carpet Review

Date: 2026-08-01

## Verdict

The repository is release-consistent for its reduced product boundary: WeChat private-chat sync, deterministic evidence corpus, DeepSeek lead analysis, native AppKit workspace, and Excel export. The unsafe native WeChat send capability has been completely removed. No fallback send channel was added.

## Root cause and removal decision

Live WeChat `4.1.12.29/269341` certification produced `EXC_BAD_ACCESS` on a `mars::stn` thread with an explicit possible pointer-authentication failure. The failing path passed a Frida-allocated fake C++ object/vtable into WeChat's internal `StartTask` pipeline. This violates the arm64e authenticated-pointer boundary and cannot be certified by offset mapping, cleanup changes, or longer timeouts.

The repository therefore no longer contains:

- Native send UI, batch editor, preview, or send status.
- Send CLI, daemon, dispatcher, state store, ACK journal, or session supervisor.
- NativeWorker, WeChat binary profiles, attach probes, Frida JavaScript sender, or certification command.
- Phase 6 send scripts/tests or packaged send resources.

Frida 16.7.19 remains solely because the bundled Chatlog dependency imports it to extract the local database key. The desktop App itself no longer attaches to WeChat.

## Cross-layer consistency

- App UI exposes only sync, business settings, DeepSeek controls, evidence review, and Excel export.
- Workspace snapshots no longer query or expose send state.
- Excel no longer contains a send-status column or validation list.
- Build scripts do not create or package NativeWorker.
- No-fallback scanning rejects native-send names and prohibited substitute transports in production sources.
- README and Agent notes describe the same reduced capability boundary.

## Verification evidence

- 62 unit tests passed.
- Ruff format/check passed.
- Python compileall passed.
- Node and all Shell syntax checks passed.
- Objective-C syntax check passed.
- Phase 0 quick build passed.
- No-fallback scan passed.
- Phase 4 native AppKit UI, render preview, and real XLSX export passed.
- Visual preview confirmed no send button or batch editor remains.
- Final DMG mounted read-only and passed deep signature, dependency, license, manifest, and AppKit smoke checks.
- Mounted DMG contains no NativeWorker, send CLI, send daemon, send store, native sender, or profiles.
- `git diff --check` passed.

Final artifact: `dist/WeChatSalesAgent-MVP-macOS-arm64.dmg`  
SHA-256: `bbd12eecf5779b249a288b0ca71075dcdaac919f0c20424c1e5bdca68284b14a`  
Size: 131,731,279 bytes

## Remaining delivery constraints

- Chatlog key extraction still requires SIP to be disabled on the authorized test Mac.
- The App is ad-hoc signed and not notarized because no Developer ID identity is available.
- Existing local SQLite databases may retain historical send tables from older builds, but no current source or packaged runtime reads, writes, displays, or dispatches them. They are deliberately not destructively migrated or deleted.
