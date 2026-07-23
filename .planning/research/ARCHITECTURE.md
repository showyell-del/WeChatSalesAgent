# Architecture Patterns

**Project:** 微信客户成交 Agent  
**Domain:** 本地微信私聊线索分析与受控原生触达的 macOS 桌面应用  
**Researched:** 2026-07-23  
**Overall confidence:** HIGH（数据、分析和队列边界）；MEDIUM（视频/文件 native 适配器仍待 Spike 验证）

## Architecture Decision

采用**原生 macOS 模块化单体 + 独立本地 Native Sender Worker**。

- 桌面主程序负责账号工作区、同步编排、本地仓库、规则预筛选、DeepSeek 分析、线索视图、Excel 导出和发送计划。
- 独立 Sender Worker 是唯一可以连接微信 native 状态的进程；Worker 内只有一个串行 `NativeSessionOwner`，四类发送适配器都必须经它执行。
- 主程序与 Worker 使用本机进程间命令通道，不开放 HTTP/Web UI，不复制 Chatlog 通用后台。
- 本地持久层是业务事实来源；Chatlog 数据能力只作为账号、取钥、解密、同步和消息读取的内部实现，不成为产品边界。
- 每个阶段都失败关闭。取钥失败不读旧数据冒充最新同步，DeepSeek 失败不改用本地猜分，原生发送失败不改用系统分享、剪贴板、键鼠模拟、Hermes 或其他通道。

```text
┌────────────────────── macOS Desktop App ──────────────────────┐
│  SwiftUI/AppKit UI                                             │
│       │ commands                         ▲ read models         │
│       ▼                                  │                     │
│  Application Use Cases / Coordinators                          │
│    ├─ Account & Sync Coordinator                               │
│    ├─ Analysis Coordinator                                     │
│    ├─ Export Coordinator                                       │
│    └─ Send Plan Coordinator ───────────────┐                    │
│       │                                     │ local IPC         │
│       ▼                                     ▼                   │
│  Local Session Repository           Durable Send Queue         │
│       │                                     │                   │
│  Rule Prefilter/Extractor                   │                   │
│       │                                     │                   │
│  DeepSeek JSON Gateway                      │                   │
│       │                                     │                   │
│  Lead Repository + Audit Log                │                   │
└─────────────────────────────────────────────┼───────────────────┘
                                              ▼
┌──────────────────── Native Sender Worker ──────────────────────┐
│  Exact Profile Gate → single NativeSessionOwner                │
│                          │ one command at a time                │
│          ┌───────────────┼───────────────┬───────────────┐      │
│          ▼               ▼               ▼               ▼      │
│       TextAdapter     ImageAdapter    VideoAdapter     FileAdapter│
│          └────────── Ack / cancel / cleanup events ─────┘      │
└────────────────────────────────────────────────────────────────┘
```

This is not a distributed system. Process separation exists only to isolate the risky Frida/native lifecycle and enforce one owner; adding services, a message broker, a local web server, or plugin abstractions would add failure modes without commercial value.

## Non-Negotiable Invariants

1. **One task, one account:** every sync, analysis run, lead snapshot, export and send plan carries an immutable `account_id`; no operation reads implicit “current account” state after it starts.
2. **Freshness is explicit:** a failed sync never advances its checkpoint or publishes its staging generation. The UI may display the last completed generation only as historical data with its actual timestamp and failed-current-sync status; it must never label it current.
3. **Evidence precedes model judgment:** DeepSeek only receives locally selected evidence bundles. Every returned conclusion and score must reference evidence IDs that existed in the request.
4. **Strict AI contract:** malformed JSON, missing fields, unknown evidence IDs, invalid score/rating combinations, or invented business facts fail that customer analysis. There is no parser repair or alternative model path.
5. **Single native owner:** only the Sender Worker may attach Frida, load scripts, allocate native objects, call native send functions, observe Ack, detach, or restart WeChat during controlled cleanup.
6. **Success requires proof:** `MMStartTask` return, hook observation, upload completion alone, or UI appearance is not success. A send succeeds only after the adapter's verified protocol Ack and required cleanup complete.
7. **Adapters are separately certified:** text, image, video and file have independent request construction, upload/callback, Ack parsing, cancellation and cleanup implementations. Changing a message type on another adapter is forbidden.
8. **No invisible recovery:** no compatibility scanning at send time, alternate offsets, fallback transport, silent retry, cached AI response substitution, or stale-data substitution.
9. **Audit events are append-only:** state projections may be updated, but the events explaining account, sync, analysis, export and send outcomes are never overwritten.
10. **UI exposes only certified capabilities:** an attachment type is absent from the send composer until its live verification matrix passes for the exact WeChat profile.

## Component Boundaries

| Component | Responsibility | Owns | Must not do | Communicates with |
|---|---|---|---|---|
| Desktop UI | Account selection, time-range input, dashboard, lead table/detail, evidence view, cost display, preview/confirm, queue status | Ephemeral view state only | Call Chatlog APIs, DeepSeek or Frida directly; expose SQL/native debug UI | Application coordinators and read models |
| Application coordinators | Execute explicit use cases and enforce account/run IDs and state transitions | Operation lifecycle | Contain database, prompt or native-hook details | Repositories, gateways, audit log, Sender Worker client |
| Account Discovery | Discover local WeChat accounts/data roots and return stable identities | `AccountIdentity` discovery result | Select silently when multiple accounts exist | Account & Sync Coordinator |
| Profile Gate | Verify architecture, exact WeChat version/build, full dylib hash and arm64 slice hash before key extraction or send | Immutable `NativeProfile` result | Probe alternate offsets or continue on partial match | Key Acquisition, NativeSessionOwner |
| Key Acquisition & Verification | Attach through the one approved Frida/key path, obtain candidate keys, verify each key against each expected database | `DatabaseKeyVerification` records | Reuse unverified keys; run as root; hide the failing database | Profile Gate, Decryption & Sync |
| Decryption & Incremental Sync | Produce a validated local generation from first decrypt or WAL/incremental input, then atomically advance checkpoint | `SyncRun`, staging generation, `SyncCheckpoint` | Mutate the published generation in place; advance on partial failure | Local Session Repository, Audit Log |
| Local Session Repository | Normalize contacts, sessions and messages for one account; page private history; resolve immutable evidence excerpts | Conversation/message records and evidence references | Expose raw SQL/database pages; mix accounts | Rule Prefilter, evidence detail, Sync |
| Rule Prefilter & Deterministic Extractor | Exclude non-human/non-private/empty sessions; extract contact details, needs, budget, region, time and positive/negative signals | `CandidateBundle`, `EvidenceItem`, deterministic fields | Assign model-only conclusions or upload full history by default | Local Session Repository, DeepSeek Gateway |
| DeepSeek JSON Gateway | Build stable-prefix requests from business config and candidate evidence; call configured model; record token/cost usage; validate exact schema and evidence references | `AnalysisAttempt` request/response envelope | Repair malformed output, invent defaults, invoke another model, send complete six-month history | Analysis Coordinator, Lead Repository, Audit Log |
| Lead Repository | Store versioned lead snapshots, score bands, evidence links, obstacles, suggested action, draft activation copy and analysis lineage | `LeadSnapshot`, `AnalysisRun` | Rewrite prior run results or detach a lead from its source account/generation | Dashboard/table/detail read models, export, send plan |
| Excel Exporter | Generate a filterable customer activation workbook from a selected immutable lead snapshot/run | `ExportRun` and file checksum | Query raw chat databases or add facts not present in the snapshot | Lead Repository, Audit Log |
| Send Plan Coordinator | Freeze selected targets, per-customer edited text, ordered attachments and business configuration after preview/confirmation | Immutable `SendPlan`, ordered `SendCommand`s | Send directly; alter confirmed content; enqueue an uncertified type | Lead Repository, durable queue, audit log |
| Durable Send Queue | Persist command order and delivery/cleanup states before IPC dispatch | `SendCommand`, `SendAttempt` state projections | Execute multiple running commands; auto-retry failed commands | NativeSessionOwner, UI read model, Audit Log |
| NativeSessionOwner | Enforce one active WeChat/Frida generation, exact profile, serial dispatch, Ack correlation, cancellation and full release | Frida session/script/native generation and active command lease | Share native state, accept a second running command, load mismatched profile | Queue, four adapters, health checker |
| Text Adapter | Build and verify native text task lifecycle | Text-specific payload/Ack parser | Handle other media types | NativeSessionOwner |
| Image Adapter | Stage image, execute image upload/task, map callback/Ack, remove staging file | Image-specific native objects and staging | Treat video/file as image | NativeSessionOwner |
| Video Adapter | Implement real video upload, thumbnail/media metadata, final video message, Ack/cancel/cleanup | Video-specific native objects and staging | Send video as file or image | NativeSessionOwner |
| File Adapter | Implement real file upload and downloadable file message with exact name/size/content verification | File-specific native objects and staging | Use invalidated simple `uploadappattach -> sendappmsg` path | NativeSessionOwner |
| Audit Log | Append structured, correlated facts for user-visible diagnostics and acceptance tests | `AuditEvent` stream | Store secrets or replace domain state | Every coordinator, gateway and Worker |

## Core Data Model

The persistent identifiers are part of the architecture, not implementation detail. They prevent cross-account analysis and wrong-recipient sends.

| Record | Required identity/lineage | Key content |
|---|---|---|
| `AccountIdentity` | `account_id` | WeChat account identity, source directory, verification state |
| `NativeProfile` | `profile_id` | bundle version, build, architecture, full hash, arm64 hash, certified adapter versions |
| `SyncRun` | `sync_run_id`, `account_id` | mode, started/completed timestamps, failing step/database, published generation |
| `SyncCheckpoint` | `account_id`, database ID | last committed generation and upstream/WAL position |
| `Conversation` / `Message` | `account_id`, stable source IDs | normalized private-chat metadata and message content/media references |
| `EvidenceItem` | `evidence_id`, message source ID, generation | exact excerpt, timestamp, sender, deterministic signal type |
| `AnalysisRun` | `analysis_run_id`, `account_id`, generation, config version | model/base URL, schema version, token counts, cost, run status |
| `LeadSnapshot` | lead ID, analysis run, contact/conversation ID | extracted fields, 0–100 intention score, band, evidence IDs, obstacle, action, activation draft |
| `SendPlan` | `send_plan_id`, account ID, analysis run ID | confirmed immutable customer ordering and final content hashes |
| `SendCommand` | command ID, plan ID, recipient ID, sequence | one text/media operation and attachment checksum |
| `SendAttempt` | attempt ID, command ID, native profile ID | delivery state, Ack facts, cancellation facts, cleanup facts |
| `AuditEvent` | monotonic event ID, correlation ID | category, event, timestamp, safe structured fields |

API keys and verified database-key material do not belong in business tables or logs. Store DeepSeek credentials and sensitive key material in the macOS credential boundary; repositories store only references and verification metadata needed to explain state.

## Data Flow

### 1. Account, Key, Decrypt and Incremental Sync

```text
Discover accounts
  → user selects explicit account_id
  → verify exact app/build/full dylib/arm64 hashes
  → acquire candidate key
  → verify key independently against every required database
  → decrypt/copy into a new staging generation
  → apply WAL/incremental changes to staging
  → validate expected databases and repository invariants
  → atomic publish generation + checkpoint
  → refresh local read models
```

The published repository is generation-based. A sync run writes staging data and only makes it visible after all required databases validate. Failure records the exact database/step, discards the incomplete generation, and leaves the previous generation labeled with its real completion time. Account switching creates a different repository scope; it never rebinds an in-flight analysis or send plan.

Key extraction and message sending both depend on `ProfileGate`, but they do not share a live Frida session. Sync/key tasks and send tasks are mutually exclusive at the application coordinator level so two native owners cannot attach concurrently.

### 2. Local Rule Prefilter and DeepSeek Analysis

```text
account_id + published generation + time range
  → page sessions/messages from Local Session Repository
  → deterministic conversation eligibility filter
  → deterministic field/signal extraction
  → candidate evidence bundle with evidence_id values
  → token/cost estimate shown for the run
  → strict DeepSeek JSON request
  → JSON Schema/domain/evidence/business-claim validation
  → versioned LeadSnapshot or explicit failed AnalysisAttempt
  → dashboard/table/detail projections
```

Eligibility filtering removes group, official/service, bot/system and ineffective conversations before any API request. The evidence bundle contains only the excerpts necessary to judge the candidate plus stable business configuration. The stable system prefix and schema are versioned separately from per-candidate evidence so prompt changes remain auditable.

Validation is ordered: JSON parse → schema → enum/range constraints → evidence ID membership → score-band consistency → business-fact/forbidden-claim checks. A failure produces no lead snapshot for that attempt and cannot be represented as a low score. The UI shows the failed customer/run and reason so the user can explicitly rerun after correcting configuration.

### 3. Lead Views and Excel Export

Dashboard, table and detail screens are projections over `LeadSnapshot` plus actual send states; they do not recompute scores. Opening evidence resolves `EvidenceItem` against the same account and source generation. If source content is missing or mismatched, the detail is an integrity error, not silently replaced by nearby text.

Excel export takes `analysis_run_id` (and optional selected lead IDs) and writes one immutable snapshot. It includes actionable fields, evidence excerpts/IDs, analysis time, actual token/cost figures and send status where requested. Generate to a unique temporary file, validate workbook structure, calculate SHA-256, then atomically publish the chosen destination. A failed export leaves no apparently complete workbook.

### 4. Preview, Confirm and Serial Native Send

```text
selected LeadSnapshots
  → per-customer editable final text + ordered attachments
  → attachment/profile/recipient preflight
  → complete preview and explicit confirmation
  → persist immutable SendPlan and queued commands
  → Worker accepts exactly one command lease
  → adapter prepare → native start/upload → correlated Ack
  → adapter cleanup → WeChat health check
  → persist terminal delivery + cleanup facts
  → release lease → next command
```

Confirmation freezes recipient ID, rendered text, attachment path/name/type/size/SHA-256, command order and native profile. If a local attachment changes after confirmation, preflight fails that command; content is never silently reread and sent under an old preview.

The Worker returns events carrying `command_id`, `attempt_id`, native task ID and generation ID. The queue accepts an event only when all correlations match the active lease. After process loss, any command that was `running` becomes an explicit indeterminate/failed attempt requiring cleanup and user review; it is never replayed automatically because delivery may already have occurred.

## Send State Model

Delivery and cleanup are related but separate facts. This avoids reporting “failed” while hiding a dirty Frida session.

```text
queued ──cancel before lease──→ cancelled
   │
   └→ running → waiting_ack ──valid Ack──→ delivered
          │          │                       │
          │          └─timeout/bad Ack────→ failed
          └─cancel requested→ cancelling ─→ cancelled or delivered (Ack wins)

Every running path → cleanup_pending → cleaned | cleanup_failed
```

- User-visible `succeeded` requires `delivery=delivered` and `cleanup=cleaned`.
- User-visible `failed` retains its concrete phase, native task ID, Ack/parser facts and cleanup result.
- A queued customer can be cancelled without touching native state.
- A running cancellation is complete only after the type-specific abort/no-further-send condition and cleanup are observed. If a valid Ack arrives first, the record remains delivered; cancellation cannot rewrite reality.
- `cleanup_failed` closes the Worker generation, blocks later commands, performs the one validated controlled cleanup procedure, and requires a passing WeChat health check before a new generation can start. It does not switch transport or retry the message.

## Native Adapter Contract

All four adapters implement the same lifecycle interface, but no payload/upload/Ack implementation is shared across message types merely for convenience.

```text
validate(profile, recipient, content) -> ValidatedCommand
prepare(validated)                    -> NativeResources
start(resources)                      -> NativeTaskIdentity
observe(task)                         -> typed progress/Ack events
cancel(task)                          -> verified cancellation outcome
cleanup(resources)                    -> cleanup report
```

Required adapter certification evidence:

1. Exact WeChat version/build/full dylib/arm64 slice gates pass before hooks load.
2. Instruction/object-layout observations match the recorded machine-readable profile.
3. Async-retained objects use persistent native allocation (`calloc`/`mmap`); ordinary Frida heap is not an allowed alternative.
4. Recipient receives the correct native message type. File name/length/content or video playability/metadata are verified at the receiver.
5. Ack is distinguishable from `MMStartTask`, serializer entry and upload progress.
6. Timeout, invalid Ack and cancellation reach deterministic terminal and cleanup states.
7. One hundred sequential real sends complete without wrong recipient, crash, sustained high CPU, lost login or residual helper/script/session/staging resources.

The existing Spike proves that `uploadappattach` and direct `sendappmsg` file tasks can return from `MMStartTask` without reaching `Req2Buf`, serializer or `Buf2Resp`; that path is architecturally excluded. File and video work must begin from observed native media upload/callback lifecycles and earn separate PASS results before their capabilities are registered.

## Audit and Diagnostics

Use a structured append-only event record:

```json
{
  "event_id": 1842,
  "timestamp": "2026-07-23T12:00:00.000Z",
  "category": "native_send",
  "event": "ack_validated",
  "account_id": "acct_...",
  "correlation_id": "attempt_...",
  "command_id": "cmd_...",
  "safe_fields": {"adapter": "image", "native_task_id": 12345}
}
```

Events must cover account discovery/selection, every profile gate, each database key verification, sync generation publication/failure, candidate exclusion counts, evidence bundle hashes, DeepSeek request/schema versions and token usage, lead publication, export checksum, queue transitions, native callbacks/Ack, cancellation, cleanup and health check. Never log database keys, API keys, full raw chat payloads or attachment contents.

User-facing diagnostics map stable error codes to precise steps, for example `SYNC_KEY_VERIFY_FAILED(database_id)`, `AI_EVIDENCE_REFERENCE_INVALID(customer_id)`, `SEND_PROFILE_HASH_MISMATCH`, and `SEND_CLEANUP_FAILED(attempt_id)`. Raw native details remain in the local audit package, not in a debug page.

## UI Architecture

The macOS UI is a projection and command surface, not an alternate business-logic layer.

- A single app navigation hierarchy: Connection → Analysis → Leads → Send/Status.
- Screen view models subscribe to typed read models keyed by `account_id` and run/plan ID.
- Long operations expose real stage, counts and failures from persisted operation state; fake progress percentages are forbidden.
- Account switching is disabled for confirmed/running sends and cannot mutate an open run's binding.
- Only adapters whose certification registry contains PASS for the active exact profile appear in the attachment picker.
- No embedded browser, localhost server, WebView-hosted dashboard, generic database explorer or native-hook debug panel.

## Patterns to Follow

### Pattern 1: Transactional Generation Publish

**What:** Build each sync in a staging generation, validate it, then atomically publish the generation and checkpoint together.  
**Why:** A half-applied WAL or one bad database cannot contaminate a previously valid customer repository.  
**Use for:** First decrypt, incremental sync and derived repository rebuilds.

### Pattern 2: Ports with Narrow Adapters

**What:** Business use cases depend on narrow repository/gateway/worker interfaces; Chatlog internals, DeepSeek transport, Excel implementation and Frida scripts stay behind adapters.  
**Why:** It permits direct tests of commercial workflows while preventing infrastructure details from leaking into UI and domain logic.  
**Constraint:** Do not turn this into a generic plugin framework. There are four explicit send adapters and one explicit AI gateway.

### Pattern 3: Immutable Evidence and Run Lineage

**What:** Scores, extracted fields and activation copy refer to immutable evidence IDs and an analysis run/config version.  
**Why:** A user can audit why a customer appeared, and later syncs cannot silently change old evidence.

### Pattern 4: Single-Writer Actor for Native State

**What:** One Worker process and one serial owner control the complete Frida/native generation.  
**Why:** The native client holds asynchronous objects and callbacks; concurrent shared state risks wrong task correlation, dirty unload and wrong-recipient sends.

### Pattern 5: Durable Intent Before Side Effect

**What:** Persist confirmed command content and `queued` state before sending it to the Worker; persist every callback before dispatching the next command.  
**Why:** Crashes can be diagnosed without guessing whether the side effect occurred. No uncertain command is replayed automatically.

## Anti-Patterns to Avoid

### Web Shell Around Chatlog

**Why bad:** Preserves the wrong product surface, exposes generic APIs/debug pages and duplicates state between a browser service and desktop UI.  
**Instead:** Extract only internal data/native capabilities behind desktop use cases.

### Shared “Universal Media” Sender

**Why bad:** Image, video and file uploads have different objects, callbacks, metadata and Acks. Re-labeling a task can return from `MMStartTask` without sending anything.  
**Instead:** Keep four named adapters with independent certification.

### Offset Discovery During Production Send

**Why bad:** A unique byte-pattern match is not proof of object layout or live correctness and can crash or mis-send.  
**Instead:** Load only a pre-validated immutable profile whose exact hashes match.

### Best-Effort AI Parsing

**Why bad:** Regex extraction, missing-field defaults or local guessed scores can turn malformed output into fabricated commercial facts.  
**Instead:** Strict schema/evidence/business-rule validation and explicit failed attempts.

### In-Place Sync Mutation

**Why bad:** A failed database/WAL step leaves an ambiguous mixture of old and new messages.  
**Instead:** Staging generation plus atomic publication.

### Automatic Retry After Ambiguous Send Failure

**Why bad:** Timeout does not prove non-delivery; replay can duplicate messages.  
**Instead:** Mark the attempt failed/indeterminate, complete cleanup, show evidence, and require explicit user action after review.

## Build Order and Dependencies

```text
1. Domain IDs, operation states, audit schema, local persistence
   ├→ 2. Account discovery + exact profile gate + key verification
   │    └→ 3. Decrypt/incremental sync + generation repository
   │         └→ 4. Private-session filter + deterministic extraction
   │              └→ 5. DeepSeek strict JSON/evidence validation
   │                   └→ 6. Lead repository + dashboard/table/detail + Excel
   └→ 7. Durable send plan/queue + isolated single NativeSessionOwner
        ├→ 8a. Re-certify text adapter
        ├→ 8b. Re-certify image adapter
        ├→ 8c. Video Spike → adapter certification
        └→ 8d. File Spike on new media path → adapter certification
             └→ 9. Preview/confirm integration + cancellation/cleanup UI
                  └→ 10. Real-account six-month E2E + 100-send acceptance
```

### Ordering Rationale

1. **Persistence, IDs and audit first:** every later failure must already have a durable, correlated representation; retrofitting lineage after AI/send work invites ambiguity.
2. **Data freshness before analysis:** rules and AI cannot be accepted against an unverified account or partial generation.
3. **Deterministic extraction before AI:** it reduces privacy exposure/cost and gives evidence IDs required for strict validation.
4. **Lead model before UI/export:** dashboard, table, detail and Excel must be projections of one source of truth, not separate calculations.
5. **Queue/owner skeleton before media integration:** each adapter is developed against the final serial lifecycle and cancellation contract, preventing later concurrency rewrites.
6. **Adapter certification is parallelizable in research but independent at release:** video/file failures do not change their technical contract and do not authorize fallback; the feature remains absent until PASS.
7. **End-to-end acceptance last:** the 100-target run is meaningful only after exact profile, Ack correlation, cleanup, health checks and audit events are all implemented.

## Phase Gates

| Phase | Exit gate | Blocks |
|---|---|---|
| Account/profile | Exact account selected; version/build/full/arm64 hashes verified; mismatch test fails closed | Key extraction and all native send |
| Key/sync | Every required database key verified; first and incremental generations publish atomically; failure identifies step/database | Analysis |
| Local analysis | Human private-chat eligibility and deterministic fields pass labeled fixtures; evidence IDs resolve exactly | DeepSeek calls |
| AI analysis | Strict JSON, evidence membership, business-claim and token/cost tests pass; malformed outputs create failures, not leads | Lead views/export/send copy |
| Lead/UI/export | Dashboard/table/detail agree on the same run; Excel validates and matches source snapshot | Commercial review workflow |
| Queue/owner | One active lease enforced across process restart; ambiguous attempt never auto-replays; cancellation/cleanup transitions verified | Native adapter release |
| Each send adapter | Exact-profile receiver verification, typed Ack, cancellation, cleanup, and 100 sequential sends pass | Visibility of that specific send type |
| Full product | Real business account completes six-month sync → analysis → audited export → confirmed personalized send with no wrong recipient/resource residue | v1 release |

## Capacity and Performance

Scale vertically on the local machine; do not add distributed infrastructure.

| Concern | Initial business case (~1K contacts / six months) | Larger local history | Design response |
|---|---|---|---|
| Message reads | Paged by conversation/time | Millions of messages | Indexed account/conversation/time access; streaming pages, never load full history into UI memory |
| Rule extraction | Per candidate conversation | Many candidates | Deterministic incremental pipeline keyed by source generation/config version |
| DeepSeek requests | Candidates only | Cost/rate constrained | Evidence compression, stable prefix, bounded request concurrency; never bypass strict validation |
| UI table | Hundreds/thousands of leads | Tens of thousands | Repository-side filtering/sorting and paged read models |
| Excel | One lead snapshot | Large exports | Streaming row generation, atomic publish, checksum |
| Sending | About 100 targets | Larger campaigns | Always one native command at a time; throughput must not weaken owner/Ack/cleanup guarantees |

## Research Flags

- **Video adapter — HIGH research need:** capture manual video upload/task/callback, thumbnail and CDN/AES/MD5/duration/dimension mapping, typed Ack and cancellation on the exact 4.1.11.55 profile.
- **File adapter — HIGH research need:** the tried simple app-attach path is invalidated. Discover the real media upload/final message lifecycle and verify receiver filename, length and SHA-256.
- **Serialized lifecycle — HIGH research need:** prove one Worker generation across text/image/video/file, cancellation races, timeout, controlled cleanup and 100-command run.
- **Data sync — MEDIUM research need:** define exact atomic generation/checkpoint mechanics for Chatlog's decrypted databases and WAL behavior before implementation.
- **DeepSeek contract — MEDIUM research need:** freeze the exact JSON schema, model identifier and token accounting behavior against current official API behavior before phase planning.
- **Desktop UI/Excel — LOW research need:** standard local application patterns once domain read models and export contract are fixed.

## Sources

### Project sources (HIGH confidence)

- `.planning/PROJECT.md` — product boundary, constraints, validated native-send facts and roadmap intent.
- `.planning/REQUIREMENTS.md` — complete data, analysis, UI, AI, export and send requirements.
- `.planning/notes/chatlog-infrastructure-decisions.md` — Chatlog capabilities to retain/delete and reusable send lifecycle sources.
- `Agent.md` — locally verified Chatlog APIs, Frida environment, exact WeChat profile and native sender rules.
- `.planning/spikes/CONVENTIONS.md` — native profile, Ack, allocation and cleanup gates.
- `.planning/spikes/MANIFEST.md` — video/file/serialized lifecycle acceptance criteria and current verdicts.
- `.planning/spikes/001-native-file-send/README.md` — invalidated simple file path and next investigation direction.
- `.planning/spikes/001-native-file-send/events.jsonl` — successful read-only profile discovery and clean detach evidence.
- `.planning/spikes/001-native-file-send/file-send-events.jsonl` — `MMStartTask` return without `Req2Buf`/Ack plus unload/detach timeout evidence.

## Confidence Assessment

| Area | Confidence | Reason |
|---|---|---|
| Desktop/module boundaries | HIGH | Directly derived from explicit product and no-Web constraints; components map one-to-one to requirements |
| Account/sync/repository flow | HIGH for boundary, MEDIUM for storage mechanics | Required failure semantics are explicit; exact Chatlog WAL/decryption implementation still needs phase design |
| Rule/AI/lead flow | HIGH for contract | Requirements explicitly demand local prefilter, necessary evidence and strict JSON; exact final schema/model behavior remains to freeze |
| Single-owner send architecture | HIGH | Explicit requirement and validated native async/allocation/cleanup evidence support serial ownership |
| Text/image adapters | MEDIUM-HIGH | Upstream implementations exist but require production re-certification under the final owner/profile contract |
| Video/file adapters | LOW for implementation, HIGH for required boundary | No verified implementation yet; file experiment definitively excludes one path, so independent certification remains mandatory |
| Build ordering | HIGH | Follows hard data lineage and side-effect dependencies; no phase depends on an unverified fallback |
