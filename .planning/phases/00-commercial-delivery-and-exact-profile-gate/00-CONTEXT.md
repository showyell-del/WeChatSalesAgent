# Phase 0: Commercial Delivery and Exact Profile Gate - Context

**Gathered:** 2026-07-23
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

This phase proves the product can be delivered as a commercially installable macOS Apple Silicon desktop app with a narrow native WeChat instrumentation path. It must validate the exact WeChat 4.1.11.55 profile, bundle and run the native worker, attach/detach cleanly, acquire/read minimally, and complete one receiver-visible text send smoke test with typed Ack and cleanup.

This phase does not implement the lead-analysis product, customer table, Excel export, video sending, file sending, or batch send lifecycle. Those later capabilities may only build on gates proven here.

</domain>

<decisions>
## Implementation Decisions

### Commercial packaging gate
- **D-01:** Build a native macOS arm64 desktop skeleton, not a Web UI or local browser console.
- **D-02:** Package boundaries must account for the app shell, Go core/helper, and bundled Python/Frida worker from the start.
- **D-03:** Signing/notarization/stapling feasibility is a phase gate. Development-only attach success is not enough.

### Exact WeChat profile gate
- **D-04:** All key extraction and send operations must fail closed unless the running WeChat process matches version `4.1.11.55`, build `269111`, full `wechat.dylib` SHA-256 `c2a4794b343625a8013752095e76bc688acd42d48f30001a255620db2fc542a9`, and arm64 slice SHA-256 `da53625065d283d748f959627f5e4d724eb786f2911f49c91a72cc12f17d30f7`.
- **D-05:** Unsupported macOS architecture, SIP/security posture, WeChat version, dylib hash, Frida attach, key/read, send, Ack, cleanup, and helper-residue conditions must report explicit terminal diagnostics.

### Native worker lifecycle
- **D-06:** One Python/Frida worker owns WeChat attach, script load, command, unload, detach, helper cleanup, and health checks.
- **D-07:** No Hermes, share sheet, clipboard, keyboard/mouse automation, media substitution, retry fallback, or unsupported-version compatibility branch is allowed.
- **D-08:** Native async objects that WeChat may retain must use native persistent allocation (`calloc`/`mmap`), not Frida heap lifetime assumptions.

### Minimal smoke scope
- **D-09:** Phase 0 only needs one receiver-visible minimal text send with typed Ack and cleanup to prove the packaged instrumentation path.
- **D-10:** Text/image/video/file adapter certification remains Phase 5. Phase 0 must not expose or imply certified attachment support.

### the agent's Discretion
- The exact skeleton project layout, CLI subcommands, helper IPC shape, diagnostic JSON schema, and local verification commands are at the agent's discretion, provided the implementation stays simple and supports later phases without fallback branches.

</decisions>

<specifics>
## Specific Ideas

- Treat Phase 0 as a commercial feasibility gate, not polish.
- Use existing Chatlog Alpha and spike evidence only as implementation references; do not copy the Chatlog Web console.
- Keep verified paths updated in `Agent.md` as soon as they are proven.

</specifics>

<canonical_refs>
## Canonical References

### Product and phase scope
- `.planning/PROJECT.md` - Core value, platform boundary, no-fallback constraints, and key decisions.
- `.planning/REQUIREMENTS.md` - Exact platform requirements, send restrictions, and traceability.
- `.planning/ROADMAP.md` - Phase 0 goal, success criteria, and dependencies.
- `.planning/research/SUMMARY.md` - Roadmap rationale, non-negotiable gates, and risk ordering.

### Verified native facts
- `Agent.md` - Verified Chatlog API, local Frida/profile facts, exact offsets, and invalidated native file path.
- `.planning/spikes/MANIFEST.md` - Spike status and pending native verification direction.
- `.planning/spikes/001-native-file-send/README.md` - File send evidence, invalidated `uploadappattach -> sendappmsg` path, and lifecycle findings.

### Source references
- `chatlog_2f54920_darwin_arm64/README.md` - Installed Chatlog Alpha package behavior and user flow.
- `chatlog_2f54920_darwin_arm64/chatlog-darwin-arm64` - Local Chatlog Alpha binary used for verified API/key/read references.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Chatlog Alpha binary and README: useful for validating the current local data/key/read path and for comparing command behavior.
- Spike scripts in `.planning/spikes/001-native-file-send/`: useful as evidence and diagnostic references, not as production file-send implementation.

### Established Patterns
- Exact profile gate must use both full dylib and arm64 slice hashes.
- Failed native attempts can dirty Frida/WeChat lifecycle; cleanup and controlled restart behavior must be explicit and verified.
- `uploadappattach -> sendappmsg` is invalidated and must not be retained as a production path.

### Integration Points
- Future SwiftUI app shell launches and supervises the Go core/helper.
- Future Go core owns diagnostics, product state, profile gate orchestration, and user-visible failure classes.
- Native Python/Frida worker exposes only narrow, typed operations for profile probe, attach/detach, key/read smoke, text-send smoke, and cleanup.

</code_context>

<deferred>
## Deferred Ideas

- Account/key/sync UI and full data generations - Phase 1.
- Deterministic lead corpus and evidence index - Phase 2.
- DeepSeek structured analysis and cost ledger - Phase 3.
- Dashboard, customer table, detail panel, and Excel export - Phase 4.
- Text/image/video/file adapter certification - Phase 5.
- Batch send composer, immutable SendPlan, serial queue, and 100-target lifecycle - Phase 6 and Phase 7.

</deferred>

---

*Phase: 00-commercial-delivery-and-exact-profile-gate*
*Context gathered: 2026-07-23*
