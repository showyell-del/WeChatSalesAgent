# Project Research Summary

**Project:** 微信客户成交 Agent
**Domain:** macOS Apple Silicon 本地微信私聊线索分析与原生受控触达桌面 Agent
**Researched:** 2026-07-23
**Confidence:** HIGH for product/data/AI/UI/export boundaries; MEDIUM for signed Frida packaging; LOW until verified for native video/file adapter implementation

## Executive Summary

This product is a professional native macOS desktop Agent for local merchants who close sales through WeChat private chats. It should be built as a narrow, auditable activation workflow: connect one verified WeChat business account, build a fresh local private-chat dataset, extract deterministic customer facts, ask DeepSeek only for structured judgments over necessary evidence, present a dashboard/table/detail workspace, export Excel, then send confirmed personalized text and attachments through verified native adapters. It is not a Web UI, generic Chatlog console, CRM, RAG system, or browser-hosted admin panel.

The recommended implementation is a native SwiftUI/AppKit shell over a Go core and a separately bundled Python + Frida native sender worker. Go owns product truth, SQLite persistence, Chatlog-derived sync, deterministic extraction, DeepSeek transport, Excel export, durable queues, and audit state. Swift owns presentation only. The Python worker is the only process that attaches to WeChat and it must execute native sends serially through one `NativeSessionOwner`. All native capability is locked to WeChat `4.1.11.55` build `269111`, full `wechat.dylib` SHA-256 `c2a4794b343625a8013752095e76bc688acd42d48f30001a255620db2fc542a9`, and arm64 slice SHA-256 `da53625065d283d748f959627f5e4d724eb786f2911f49c91a72cc12f17d30f7`.

The main risk is not the lead table or DeepSeek schema; it is commercial deliverability of native WeChat instrumentation and type-correct video/file sending. The roadmap must therefore front-load packaging/profile gates and native media spikes instead of discovering late that a polished UI exposes unverified send types. No fallback, degradation, hidden compatibility branch, automatic retry, parser repair, old snapshot substitution, system share sheet, clipboard, key simulation, Hermes path, or media-type substitution is acceptable. If a capability is not proven by exact-profile receiver-visible delivery, typed Ack, cancellation, cleanup, and health checks, it must be absent from the product.

## Key Findings

### Recommended Stack

Build one native desktop application with clear process boundaries: SwiftUI/AppKit for macOS UI, Go for the long-lived business/data core, SQLite for local product state, Excelize for `.xlsx`, direct typed Go HTTP calls for DeepSeek, and a bundled CPython + Frida worker for the narrow native instrumentation path. This preserves the already validated Chatlog/Go and Python/Frida facts while avoiding Web runtime, duplicate stores, SDK retries, and unsupported platform branches.

**Core technologies:**
- **Xcode 16.4 / Swift 6 / SwiftUI + AppKit bridges:** native macOS 15 arm64 UI, drag/drop, table, detail, settings, confirmation, file picker, and Keychain integration.
- **Go 1.26.5:** product core, coordinators, persistence, Chatlog extraction, deterministic rules, DeepSeek gateway, Excel export, audit log, and durable send queue.
- **SQLite via `github.com/mattn/go-sqlite3` v1.14.32:** single app-owned product database with WAL, foreign keys, migrations, stable IDs, immutable evidence, and send state.
- **Excelize v2.11.0:** first-class `.xlsx` customer activation and send-result exports without Python spreadsheet dependencies.
- **Direct `net/http` DeepSeek client:** explicit model, timeout, response-size, JSON, usage, cost, and failure handling; no SDK-level retries or stale model aliases.
- **Bundled CPython 3.13.14 + Frida 16.7.19 + GumJS agent:** one signed native worker that owns WeChat attach/load/send/cancel/release/health for the exact verified profile.

**Critical version requirements:**
- macOS Apple Silicon only; no Intel, Rosetta, Windows, or universal compatibility work.
- Exact WeChat target: `4.1.11.55` build `269111` with both full dylib and arm64 slice hashes matching the verified values above.
- Frida 16.7.19 is the validated baseline; any Frida or profile change requires a full native validation matrix.
- DeepSeek default should be `deepseek-v4-flash` in non-thinking JSON mode, with model/base URL/pricing explicitly configured and recorded.

### Expected Features

首版必须是一条完整成交激活闭环，而不是功能拼盘。The table, dashboard, evidence detail, Excel export, DeepSeek interface, and one-click batch sending are all preserved, but only as projections over verified local state and certified native capabilities.

**Must have (table stakes):**
- **Single-account connection and health:** account discovery, exact profile gate, key acquisition, per-database verification, account status, and explicit failure step.
- **Fresh decrypt and incremental sync:** frozen published generations; failed sync cannot advance checkpoint or label old data as current.
- **Private-chat filtering:** deterministic exclusion of groups, official/service/system/bot sessions and ineffective conversations.
- **Deterministic field extraction:** phone, WeChat ID, age/grade, region, time, budget, needs, obstacles, positive/negative signals, each tied to immutable evidence.
- **DeepSeek structured analysis:** strict JSON, 0-100 intention score, four bands, evidence references, obstacles, suggested action, personalized activation copy, token/cost usage, and hard failure on invalid output.
- **Business fact configuration:** products, prices, offers, address, hours, allowed claims, and forbidden claims used to constrain AI and sending copy.
- **Native desktop workspace:** compact dashboard, lead table, evidence/detail panel, filters/sorts, selected targets, send states, and no raw database/native debug UI.
- **Excel export:** filterable `.xlsx` from the selected immutable lead snapshot, including evidence, actions, drafts, cost metadata, and send result fields.
- **Preview and confirmation:** per-customer editable text, attachment summary, final target count, content hashes, and explicit confirmation before side effects.
- **Certified native sending:** text, image, video, and file each require independently verified adapter, typed Ack, cancellation, cleanup, and receiver-visible validation before appearing.
- **Single-owner serial queue:** one immutable send plan, one native command at a time, no automatic retry after unknown delivery, and explicit cleanup/health terminal state.

**Should have (competitive):**
- **Field-level evidence chain:** every score, field, obstacle, and recommendation can jump back to source evidence.
- **Local prefilter + necessary evidence upload:** lower privacy exposure and token cost while improving model input quality.
- **Cost ledger and cache visibility:** estimated and actual input/output/cache-hit/cache-miss token accounting per run.
- **Fact-claim validation:** block drafts that invent price, offer, inventory, promise, or customer need.
- **Dashboard-to-table drilldown:** every metric filters the same lead table.
- **Reproducible run snapshots:** bind account, generation, time range, business config, prompt/schema/model, evidence, and result.
- **Touch result writeback:** send result state returns to the same customer table and export.
- **Local manual labels:** record effective lead / sold / not sold for later calibration, while still calling the score "成交意向分".

**Defer (v2+ or exclude):**
- True conversion-probability calibration and predictive revenue until real outcome labels exist.
- Team CRM, custom sales pipeline, multi-user permissions, and cross-channel customer management.
- Group-chat analytics, group member ranking, Moments, Favorites, generic search, SQL browser, RAG, knowledge graph, Chatlog Web console, or debug pages.
- Any unsupported platform/version branch, media fallback, automatic unknown-Ack retry, or unverified attachment placeholder.

### Architecture Approach

Use a modular native macOS monolith with one isolated local native sender worker. The desktop app is a command/projection surface; the Go core is the single product truth; the Python/Frida worker is the only owner of native WeChat state. All critical workflows are evented, durable, account-bound, and generation-bound. Every operation fails closed and records an auditable reason instead of silently substituting data, model output, send transport, or media type.

**Major components:**
1. **Desktop UI:** connection, analysis range, dashboard, lead table/detail, evidence, cost, Excel, preview, confirmation, and send status.
2. **Application coordinators:** account/sync, analysis, export, send-plan orchestration, lifecycle transitions, and explicit run/account binding.
3. **Profile gate:** exact architecture, WeChat version/build, full dylib hash, arm64 slice hash, and instruction/profile validation.
4. **Key acquisition and sync:** verified database keys, decrypt/incremental staging generation, atomic publish, and checkpoint management.
5. **Local session repository:** normalized account-scoped conversations/messages and immutable evidence lookup.
6. **Rule prefilter/extractor:** deterministic eligibility, facts, signals, and candidate evidence bundle construction.
7. **DeepSeek JSON gateway:** stable-prefix request, strict schema/evidence/business validation, token/cost persistence, and terminal failure classes.
8. **Lead repository and read models:** versioned lead snapshots, dashboard/table/detail projections, draft copy, and analysis lineage.
9. **Excel exporter:** workbook generation from immutable lead snapshots with structural validation and atomic publish.
10. **Send plan and durable queue:** immutable target/content/attachment manifest, ordered commands, cancellation, state projections, and audit.
11. **Native Sender Worker / `NativeSessionOwner`:** one Frida generation, one command lease, adapter execution, Ack correlation, cleanup, and WeChat health.
12. **Typed send adapters:** text, image, video, and file implemented and certified independently.
13. **Audit log:** append-only account, sync, analysis, export, queue, native, cleanup, and health evidence without secrets or raw chat payload dumps.

### Critical Pitfalls

1. **WeChat profile drift:** checking only UI version or disk app path can inject into a mismatched process. Prevent by validating the actual loaded process profile, build, full dylib hash, arm64 slice hash, and instruction fingerprints before every key/send operation.
2. **Inconsistent account/database/WAL snapshot:** one decrypted database is not an account-level success. Prevent with stable account IDs, per-database key verification, staging generations, atomic publish, explicit freshness, and account-bound run invalidation.
3. **Chatlog API completeness assumptions:** one page or `limit=5000` is not the whole private-chat dataset. Prevent with full pagination, stable message IDs, snapshot boundaries, de-duplication, unknown-type failures, and explicit exclusion counts.
4. **Valid JSON but invalid business result:** JSON mode does not prove schema, evidence, or business-fact correctness. Prevent with strict schema, evidence membership, score-band, forbidden-claim, blank/truncated-output validation, and no parser repair.
5. **Evidence mismatch:** real text can still support the wrong customer, sender, time, field, or conclusion. Prevent with immutable evidence IDs bound to account/generation/message/sender/hash and server-side membership validation.
6. **Native async lifetime and fake Ack:** `MMStartTask` or upload progress is not success. Prevent with persistent `calloc`/`mmap` memory, ownership registry, typed protocol Ack correlation, cleanup terminal state, and 100-command tests.
7. **Fake video/file support:** image or invalidated appmsg paths cannot be relabeled as file/video. Prevent with independent media upload/callback/payload/Ack discovery and receiver-side content verification.
8. **Batch send drift or duplication:** previewed content may differ from sent content after config/contact/attachment changes. Prevent with immutable confirmed manifest, content hashes, stable username IDs, single owner, no auto-replay, and queue blocking on unknown outcomes.
9. **Signed package and SIP discovered too late:** development success does not prove customer installability. Prevent with an early signed/notarized/stapled skeleton gate that performs real key/read/minimum send on a clean target Mac.
10. **Privacy leakage through logs, IPC, temp files, DeepSeek payloads, or Excel:** prevent with Keychain secrets, private UDS/pipes, no HTTP console, payload hashing, no raw logs, explicit export path, and cleanup across success/failure/cancel/crash recovery.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 0: Commercial Delivery and Exact Profile Gate
**Rationale:** The whole product depends on whether a signed/notarized native instrumentation app can be installed and operate on a clean target Mac under an acceptable security posture. This must be proven before broad UI or AI work.
**Delivers:** Signed app skeleton, nested Go/Python helper packaging, Frida attach/detach, exact WeChat profile validation, SIP/security preflight, minimal key/read/send smoke test, and explicit fail-closed diagnostics.
**Addresses:** exact version/hash gate, native worker packaging, no unsupported platform branch.
**Avoids:** late packaging failure, hidden fallback transport, profile drift, and customer-installability surprise.

### Phase 1: Account, Key, and Consistent Sync Foundation
**Rationale:** Lead scoring, evidence, export, and sending are unsafe unless tied to one verified account and one fresh published data generation.
**Delivers:** account discovery, user account selection, per-database key verification, first decrypt, incremental sync, WAL/checkpoint handling, staging generation, atomic publish, data freshness UI state, and Keychain secret storage.
**Addresses:** REQ-DATA-001 through REQ-DATA-005.
**Avoids:** cross-account data, stale snapshot substitution, partial database success, key leakage, and mixed WAL state.

### Phase 2: Deterministic Private-Chat Corpus and Evidence Index
**Rationale:** Local eligibility, extraction, and immutable evidence must exist before any model judgment can be trusted or audited.
**Delivers:** full paginated private-chat traversal, group/service/system/bot exclusion, candidate counts, deterministic field extraction, signal extraction, evidence IDs, message/sender/time/hash binding, fixtures, and manual spot-check workflow.
**Addresses:** REQ-LEAD-001 through REQ-LEAD-003, evidence basis for REQ-LEAD-005.
**Avoids:** pagination loss, system-session pollution, wrong-sender fields, evidence mismatch, and AI guessing empty facts.

### Phase 3: DeepSeek Structured Analysis and Cost Ledger
**Rationale:** AI should only operate over necessary evidence and must fail loudly when its output is not semantically valid.
**Delivers:** DeepSeek settings, model/base URL/pricing config, stable prompt/schema version, evidence compression, strict JSON request/response structs, validation pipeline, usage/cost ledger, business fact/forbidden-claim validation, intention score rubric, draft activation copy, and gold-sample regression tests.
**Addresses:** REQ-AI-001 through REQ-AI-005 and REQ-LEAD-004 through REQ-LEAD-008.
**Avoids:** malformed JSON repair, evidence hallucination, invented offers, misleading "conversion probability", cost misreporting, and excessive chat upload.

### Phase 4: Native Desktop Lead Workspace and Excel Export
**Rationale:** Once lead snapshots are trustworthy, the merchant needs a dense, professional workspace to review, filter, export, and prepare confirmed follow-up.
**Delivers:** SwiftUI/AppKit panel, compact dashboard, lead table, filters/sorts, evidence detail side panel, send-status columns, cost display, current-filter `.xlsx` export, workbook validation, sensitive-export confirmation, and no raw DB/debug screens.
**Addresses:** REQ-UI-001 through REQ-UI-005 and Excel delivery.
**Avoids:** Web console drift, hidden failure states, duplicate calculations, formula/format export errors, and old-config reuse.

### Phase 5: Native Adapter Spikes and Certification Registry
**Rationale:** Text/image can be re-certified, but video/file are the highest technical risk and must be solved before the final send composer exposes those types.
**Delivers:** adapter certification registry, re-certified text adapter, re-certified image adapter, video upload/callback/Ack spike, file upload/callback/Ack spike excluding invalidated `uploadappattach -> sendappmsg`, receiver-side content checks, cancellation, cleanup, and capability visibility rules.
**Addresses:** REQ-SEND-002 and REQ-SEND-003 capability truth.
**Avoids:** fake media support, appmsg dead path retention, type substitution, unverified UI buttons, and `MMStartTask` false success.

### Phase 6: Immutable Send Plan and Single-Owner Batch Lifecycle
**Rationale:** Batch sending is dangerous unless preview, manifest, queue, Ack, cancellation, cleanup, and health state are one coherent serial system.
**Delivers:** per-customer editable final text, ordered attachments, content/attachment hashes, complete preview, explicit confirmation, immutable `SendPlan`, durable queue, one active `NativeSessionOwner`, typed command events, cancellation rules, unknown-Ack blocking, crash recovery, cleanup registry, and WeChat health checks.
**Addresses:** REQ-SEND-001 and REQ-SEND-004 through REQ-SEND-009.
**Avoids:** duplicate sends, wrong recipient, preview/send drift, auto-replay after unknown delivery, concurrent native state, and helper/session residue.

### Phase 7: Real Business Acceptance and Release Gate
**Rationale:** The product is not done until the packaged artifact succeeds with the real merchant workflow and native sending under sustained serial load.
**Delivers:** clean-Mac install, signed/notarized/stapled artifact verification, real business account six-month sync, lead analysis, evidence sampling, Excel export, personalized preview, text/image/video/file sends where certified, 100-target sequential send test, privacy scan, no wrong recipient, no duplicate, no residual helper, no sustained WeChat high CPU, and release-ready diagnostics.
**Addresses:** first-version completion standard.
**Avoids:** development-only success, scoring overconfidence, privacy residue, native lifecycle leaks, and customer-visible false readiness.

### Phase Ordering Rationale

- **Phase 0 comes first** because signing, notarization, Frida attachability, SIP/security posture, and exact process profile are commercial go/no-go risks. A polished UI cannot compensate for a package that cannot attach safely.
- **Data lineage precedes AI** because no model score or export can be trusted unless account, database, WAL, sync generation, and evidence IDs are already stable.
- **Deterministic extraction precedes DeepSeek** because it reduces privacy/cost and provides the evidence IDs required for strict validation.
- **Lead models precede UI/export** so dashboard, table, detail, and Excel are projections over the same immutable snapshot.
- **Adapter certification precedes send composer visibility** so unverified video/file buttons never reach users.
- **Queue lifecycle follows adapter contracts** because every adapter must plug into the final single-owner Ack/cancel/cleanup state machine.
- **Real-account acceptance comes last** because the 100-target run is meaningful only after exact profile, immutable manifests, typed Acks, cleanup, privacy, and package gates are in place.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 0:** signed/notarized bundled Frida worker behavior, hardened runtime entitlements, SIP/security acceptance, clean-Mac attach/key/read/send validation.
- **Phase 1:** exact Chatlog decrypted SQLite/WAL snapshot mechanics and incremental sync race behavior.
- **Phase 3:** final DeepSeek `deepseek-v4-flash` JSON schema behavior, current pricing/tokenizer, output limit, cache accounting, and provider data-retention disclosure.
- **Phase 5:** video upload, thumbnail/media metadata, CDN callbacks, file upload/final message lifecycle, typed Ack fields, receiver-side verification, and adapter bounds.
- **Phase 6:** stable Ack correlation fields across recipient/type/generation, late Ack handling, cancellation races, cleanup failure recovery, and 100-command stress behavior.
- **Phase 7:** real merchant dataset quality, evidence sampling, score-band calibration signals, privacy residue scan, and packaged artifact health.

Phases with standard patterns (skip separate research-phase unless implementation uncovers surprises):
- **Phase 2:** deterministic extraction, evidence IDs, pagination, fixture tests, and repository-side filtering are established local-data patterns once Chatlog source contracts are fixed.
- **Phase 4:** SwiftUI/AppKit table/detail/dashboard/export presentation is standard after read models and workbook contracts exist.
- **Parts of Phase 3:** direct HTTP JSON client, strict struct decoding, schema validation, and token usage persistence are standard; only provider-specific current behavior needs refresh.

## Non-Negotiable Gates

- **No profile match, no key extraction or send.**
- **No fresh completed sync generation, no analysis.**
- **No immutable evidence ID, no score, extracted field, recommendation, or draft claim.**
- **No strict DeepSeek JSON/schema/evidence/business validation, no lead snapshot.**
- **No certified adapter PASS for the exact WeChat profile, no visible attachment send capability.**
- **No typed Ack plus cleanup, no send success.**
- **No automatic retry after unknown delivery.**
- **No Web UI, generic Chatlog console, raw SQL page, native debug page, or browser-hosted dashboard.**
- **No stale snapshot, parser repair, fallback model/provider, system automation, clipboard, key simulation, Hermes, or media-type substitution.**
- **No hidden retention of invalidated `uploadappattach -> sendappmsg` file path.**

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH for Swift/Go/SQLite/DeepSeek/Excel; MEDIUM for signed Frida bundle | Native app, Go core, SQLite, Excelize, and direct DeepSeek HTTP are well supported. Bundled Python/Frida must be proven after signing/notarization. |
| Features | HIGH | Product scope is explicit and consistent across PROJECT, REQUIREMENTS, FEATURES, and spike constraints. Video/file are required but not yet verified as working capabilities. |
| Architecture | HIGH for boundaries/state model; MEDIUM for media adapter internals | Single account, generation publish, immutable evidence, strict AI, durable queue, and single native owner are strongly supported. Exact file/video internals remain spike work. |
| Pitfalls | HIGH | Risks are grounded in project spikes, native lifecycle facts, official DeepSeek behavior, Apple packaging/security requirements, and explicit no-fallback constraints. |

**Overall confidence:** HIGH for roadmap direction; MEDIUM for release feasibility until Phase 0 and Phase 5 pass; LOW for concrete video/file implementation details before dedicated spikes.

### Gaps to Address

- **Commercial installability:** prove a formally signed/notarized/stapled app with nested Frida worker can attach, key, read, send, cleanup, and pass Gatekeeper on a clean Apple Silicon Mac.
- **SIP/security acceptance:** determine whether target merchants can accept the required macOS security posture before investing heavily beyond the gate.
- **Chatlog sync consistency:** verify active SQLite/WAL copy and incremental checkpoint behavior under live WeChat writes and restarts.
- **Video native sending:** discover the real upload/task/callback/payload/Ack lifecycle and validate receiver playability, metadata, cancellation, and cleanup.
- **File native sending:** abandon the invalidated simple app-attach path; find the real file lifecycle and verify receiver filename, size, SHA-256, downloadability, Ack, cancellation, and cleanup.
- **Ack correlation:** identify fields that reliably bind `generation + command_id + task_id + recipient + message_type` for every adapter.
- **DeepSeek current behavior:** freeze schema, output limits, non-thinking configuration, pricing, cache usage fields, and data-retention disclosure at phase planning time.
- **Real business calibration:** keep "成交意向分" wording until real sold/not-sold/follow-up labels support stronger statistical claims.
- **Privacy residue:** test logs, crash reports, temp files, IPC, exports, and network payloads across success, failure, cancel, crash, and restart.

## Sources

### Primary Project Sources (HIGH confidence)
- `.planning/PROJECT.md` — product definition, core value, exact WeChat profile, native send constraints, and out-of-scope boundaries.
- `.planning/REQUIREMENTS.md` — platform, data, lead analysis, DeepSeek, UI/export, send, and first-version completion requirements.
- `.planning/research/STACK.md` — recommended Swift/Go/Python/Frida/SQLite/Excelize/DeepSeek stack, version pins, and packaging gates.
- `.planning/research/FEATURES.md` — table-stakes features, differentiators, anti-features, information architecture, MVP order, and research flags.
- `.planning/research/ARCHITECTURE.md` — modular native desktop architecture, components, invariants, data flow, send state model, adapter contract, gates, and research flags.
- `.planning/research/PITFALLS.md` — critical failure modes, prevention strategies, phase-specific warnings, and unresolved risks.
- `.planning/notes/chatlog-infrastructure-decisions.md` — Chatlog reuse/delete boundaries and native sender source constraints.
- `Agent.md` — locally verified Chatlog APIs, Frida/profile/send rules, and no-fallback project conventions.
- `.planning/spikes/MANIFEST.md` and `.planning/spikes/001-native-file-send/README.md` — file/video/lifecycle verification status and invalidated file-send path.

### Official / External Sources Referenced by Research (HIGH confidence)
- Apple Xcode, SwiftUI, Keychain, Hardened Runtime, notarization, and SIP documentation — build host, UI, secret storage, packaging, and security gates.
- Go release history and standard library documentation — Go version baseline and direct HTTP/JSON/hash/storage implementation.
- SQLite WAL documentation — persistent WAL handling and copy consistency risk.
- Excelize documentation — `.xlsx` generation, tables, styles, filters, and streaming constraints.
- Frida JavaScript/API documentation and PyPI Frida 16.7.19 files — session/script model, memory lifetime, and arm64 wheel availability.
- PyInstaller documentation — macOS packaging and Apple Silicon code-sign restrictions.
- DeepSeek API, JSON Output, Context Caching, pricing/model, usage, and error-code documentation — JSON mode, model defaults, usage accounting, cache behavior, pricing, and terminal error classes.

---
*Research completed: 2026-07-23*
*Ready for roadmap: yes, with Phase 0 and Phase 5 treated as hard feasibility gates*
