# Roadmap: 微信客户成交 Agent

## Overview

This roadmap delivers one narrow commercial workflow: prove the signed native WeChat instrumentation path first, build fresh account-bound chat data and immutable evidence, run strict DeepSeek analysis over only necessary evidence, present the merchant workspace and Excel export, certify each native send adapter before it is visible, then complete a serial confirmed-send lifecycle and real-business release gate. The product remains a macOS Apple Silicon desktop app only; no Web UI, fallback transport, stale snapshot substitution, parser repair, unsupported WeChat branch, Hermes path, clipboard, keyboard simulation, or unverified send type is allowed.

## Phases

**Phase Numbering:**
- Integer phases (0, 1, 2): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 0: Commercial Delivery and Exact Profile Gate** - Local automated gates passed; Developer ID notarization, clean-Mac install, and live WeChat text-send smoke still need human/external verification.
- [x] **Phase 1: Account, Key, and Consistent Sync Foundation** - One verified account now produces fresh account-scoped decrypted data generations with Keychain verification and atomic publish.
- [x] **Phase 2: Deterministic Private-Chat Corpus and Evidence Index** - A full 183-day corpus now contains deterministic private eligibility, inbound facts, and immutable evidence IDs.
- [ ] **Phase 3: DeepSeek Structured Analysis and Cost Ledger** - Users can generate validated intention scores, evidence-backed judgments, costs, and compliant personalized drafts.
- [ ] **Phase 4: Native Desktop Lead Workspace and Excel Export** - Users can review, filter, inspect, and export lead snapshots in a professional macOS desktop workspace.
- [ ] **Phase 5: Native Adapter Spikes and Certification Registry** - Text, image, video, and file adapters are independently certified before any attachment type can be exposed for sending.
- [ ] **Phase 6: Immutable Send Plan and Single-Owner Batch Lifecycle** - Users can preview, confirm, cancel, and serially send personalized messages with durable Ack, cleanup, and health state.
- [ ] **Phase 7: Real Business Acceptance and Release Gate** - The packaged product passes the real merchant workflow, privacy checks, and 100-target sequential send acceptance gate.

## Phase Details

### Phase 0: Commercial Delivery and Exact Profile Gate
**Goal**: A commercially installable macOS arm64 package proves the native WeChat instrumentation path can safely attach, detach, validate the exact profile, read, key, and perform a minimal verified send smoke test.
**Depends on**: Nothing (first phase)
**Requirements**: Platform boundary; exact WeChat 4.1.11.55 build 269111 profile; signed/notarized commercial feasibility gate
**Success Criteria** (what must be TRUE):
  1. A signed, notarized, stapled arm64 app artifact installs and launches on a clean Apple Silicon Mac without Gatekeeper failure.
  2. The app refuses key extraction and sending unless the running WeChat process matches version 4.1.11.55 build 269111, full dylib SHA-256, and arm64 slice SHA-256 exactly.
  3. The bundled Python/Frida worker can attach to WeChat, load a script, detach, unload, and leave no residual helper for the verified profile.
  4. The packaged artifact proves minimal key acquisition, private-chat read, and a receiver-visible minimal text send with typed Ack and cleanup.
  5. Unsupported platform, SIP/security, profile, Frida, key, read, send, and cleanup failures are shown as explicit fail-closed diagnostics with no fallback path.
**Plans**: 4/4 local plans executed; verification status `human_needed`

### Phase 1: Account, Key, and Consistent Sync Foundation
**Goal**: Users can select one verified WeChat business account and maintain fresh, account-bound decrypted chat generations without stale substitution.
**Depends on**: Phase 0
**Requirements**: REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-DATA-004, REQ-DATA-005
**Success Criteria** (what must be TRUE):
  1. User can discover local WeChat accounts and see each account's data directory, verification status, and exact failure step.
  2. User can extract and verify database keys per database, with secrets stored in Keychain and failed databases named explicitly.
  3. User can complete first decrypt and later incremental sync into a staged generation that publishes atomically only after all required databases pass.
  4. User can switch among verified historical accounts, while each analysis run is bound to exactly one selected account.
  5. A failed read, decrypt, WAL, or sync step keeps the previous generation marked old and never presents it as the latest result.
**Plans**: 1/1 complete
**UI hint**: yes

### Phase 2: Deterministic Private-Chat Corpus and Evidence Index
**Goal**: Users can build a fresh private-chat lead corpus with deterministic eligibility, extracted customer facts, and immutable evidence references before any model judgment runs.
**Depends on**: Phase 1
**Requirements**: REQ-LEAD-001, REQ-LEAD-002, REQ-LEAD-003
**Success Criteria** (what must be TRUE):
  1. User can choose a time range and the system reads all paginated one-on-one private-chat history for the selected account generation.
  2. Group chats, official accounts, service notifications, bot/system sessions, and conversations without effective interaction are excluded with visible counts.
  3. Phone, landline, WeChat ID, age, grade, region, available time, budget, explicit need, and obstacle candidates are extracted deterministically from source messages.
  4. Every extracted field and signal links to an immutable evidence ID containing account, generation, conversation, message, sender, time, and content hash.
  5. Fixture and spot-check output proves no pagination loss, no cross-account mixing, and no wrong-sender evidence binding.
**Plans**: 1/1 complete

### Phase 3: DeepSeek Structured Analysis and Cost Ledger
**Goal**: Users can obtain strict, evidence-backed DeepSeek judgments, intention bands, token costs, and compliant personalized activation drafts over only necessary candidate evidence.
**Depends on**: Phase 2
**Requirements**: REQ-LEAD-004, REQ-LEAD-005, REQ-LEAD-006, REQ-LEAD-007, REQ-LEAD-008, REQ-AI-001, REQ-AI-002, REQ-AI-003, REQ-AI-004, REQ-AI-005
**Success Criteria** (what must be TRUE):
  1. User can configure DeepSeek API Key, Base URL, model, pricing, and business facts for products, prices, offers, address, hours, allowed claims, and forbidden claims.
  2. Analysis uploads only locally filtered necessary evidence for candidate customers, never a default full half-year chat dump.
  3. Each accepted result contains strict JSON, a 0-100 "成交意向分", one of four bands, recent contact time, evidence IDs, obstacles, suggested action, and a personalized draft only for final candidates.
  4. Empty output, malformed JSON, missing fields, evidence mismatch, forbidden claims, invented prices/offers/promises, and draft needs not expressed by the customer fail the analysis with no parser repair.
  5. User can see real input/output/cache token counts, estimated cost, actual cost, cumulative cost, and the stable prompt/schema/model version for each run.
**Plans**: TBD
**UI hint**: yes

### Phase 4: Native Desktop Lead Workspace and Excel Export
**Goal**: Users can inspect trusted lead snapshots through a dense macOS desktop workspace and export a clean customer activation workbook.
**Depends on**: Phase 3
**Requirements**: REQ-UI-001, REQ-UI-002, REQ-UI-003, REQ-UI-004, REQ-UI-005
**Success Criteria** (what must be TRUE):
  1. User can view a desktop dashboard showing only customer total, high-intent count, activation-needed count, recent new leads, intention distribution, and estimated value metrics.
  2. User can filter and sort the lead table by intention band, recent contact, need, obstacle, contact info, and send status.
  3. User can open a customer detail view with evidence, extracted key facts, suggested action, and draft text without raw database structure or native debug pages.
  4. User can export the current lead snapshot to a formatted, filterable Excel workbook containing evidence, actions, drafts, cost metadata, and send-result columns.
  5. Dashboard, table, detail, and export values all derive from the same immutable snapshot and show no hidden stale or recalculated data drift.
**Plans**: TBD
**UI hint**: yes

### Phase 5: Native Adapter Spikes and Certification Registry
**Goal**: The product has a certification registry proving which native send adapters are allowed for the exact WeChat profile, with text, image, video, and file certified before the final composer exposes them.
**Depends on**: Phase 4
**Requirements**: REQ-SEND-003
**Success Criteria** (what must be TRUE):
  1. Text, image, video, and arbitrary-file adapters each have an independent certification record for the exact WeChat profile with receiver-visible delivery, typed Ack, cancellation, cleanup, and health evidence.
  2. Video certification proves real upload/callback/payload/Ack behavior, receiver playability, metadata correctness, cancellation, and cleanup.
  3. File certification proves a non-`uploadappattach -> sendappmsg` lifecycle with receiver filename, size, SHA-256, downloadability, typed Ack, cancellation, and cleanup.
  4. The runtime capability registry hides any send type whose certification is missing, expired, profile-mismatched, or failed.
  5. Certification artifacts prove no media-type substitution, no `MMStartTask`-only success, no Hermes path, no system automation, and no invalidated file path retention.
**Plans**: TBD

### Phase 6: Immutable Send Plan and Single-Owner Batch Lifecycle
**Goal**: Users can prepare, preview, confirm, cancel, and serially execute personalized batch outreach through one native session owner with durable state and verified cleanup.
**Depends on**: Phase 5
**Requirements**: REQ-SEND-001, REQ-SEND-002, REQ-SEND-004, REQ-SEND-005, REQ-SEND-006, REQ-SEND-007, REQ-SEND-008, REQ-SEND-009
**Success Criteria** (what must be TRUE):
  1. User can enter public requirements, edit each customer's personalized text, drag certified attachments into the send interface, and see type, size, target count, and content hashes before confirmation.
  2. User sees a full preview with final recipient list, target count, estimated Token impact, attachments, per-customer content, and an explicit final confirmation before any side effect.
  3. Confirmed outreach creates an immutable SendPlan and durable queue that executes one native command at a time through a single NativeSessionOwner.
  4. User can cancel individual customers while all remaining filtered leads stay in the plan unless explicitly removed.
  5. Each message records queued, running, succeeded, failed, typed Ack, cleanup, cancellation, unknown-Ack blocking, crash recovery, Frida detach, session disconnect, and WeChat health status without fallback send paths.
**Plans**: TBD
**UI hint**: yes

### Phase 7: Real Business Acceptance and Release Gate
**Goal**: The real packaged product passes the merchant workflow and sustained native-send acceptance checks before it is considered v1-ready.
**Depends on**: Phase 6
**Requirements**: First-version completion standard
**Success Criteria** (what must be TRUE):
  1. A clean-Mac install verifies the signed, notarized, stapled artifact provenance and repeats exact profile, key/read, attach/detach, cleanup, and health checks.
  2. A real business WeChat account completes six-month sync, private-chat filtering, DeepSeek analysis, evidence sampling, dashboard review, and Excel export.
  3. Manual sampling confirms each selected lead score has real evidence, contact extraction is accurate enough for the merchant workflow, and the UI still says "成交意向分" rather than statistical conversion probability.
  4. Certified text, image, video, and file sends complete receiver-visible delivery, typed Ack, cancellation, cleanup, and send-result writeback where each certification remains valid.
  5. A 100-target sequential send test completes with no wrong recipient, no duplicate send, no residual Frida helper, no persistent WeChat high CPU, no lost WeChat login state, and no privacy residue in logs, IPC, temp files, exports, or crash reports.
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 0. Commercial Delivery and Exact Profile Gate | 4/4 local | Human needed | - |
| 1. Account, Key, and Consistent Sync Foundation | 1/1 | Complete | 2026-07-23 |
| 2. Deterministic Private-Chat Corpus and Evidence Index | 1/1 | Complete | 2026-07-23 |
| 3. DeepSeek Structured Analysis and Cost Ledger | 0/TBD | Not started | - |
| 4. Native Desktop Lead Workspace and Excel Export | 0/TBD | Not started | - |
| 5. Native Adapter Spikes and Certification Registry | 0/TBD | Not started | - |
| 6. Immutable Send Plan and Single-Owner Batch Lifecycle | 0/TBD | Not started | - |
| 7. Real Business Acceptance and Release Gate | 0/TBD | Not started | - |
