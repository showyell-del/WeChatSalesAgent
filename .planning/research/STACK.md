# Technology Stack

**Project:** 微信客户成交 Agent  
**Platform:** macOS Apple Silicon only  
**Researched:** 2026-07-23  
**Overall confidence:** HIGH for UI/core/data/API/export; MEDIUM for notarized Frida packaging until a signed release artifact passes the real-machine gate

## Recommendation in One Sentence

Build a native **SwiftUI shell** around one long-lived **Go core service**, and keep **Python + Frida JavaScript** as a narrow, bundled native-instrumentation worker only; store product state in one app-owned SQLite database, call DeepSeek through a small typed Go HTTP client, and generate `.xlsx` with Excelize.

This preserves the already validated Chatlog/Go and Python/Frida paths while keeping the user-facing app genuinely native. It deliberately avoids a web runtime, a second application data model, and SDK abstractions that add no product value.

## Recommended Stack

### Desktop UI and macOS Integration

| Technology | Pinned version / target | Purpose | Why this choice | Confidence |
|---|---|---|---|---|
| Xcode | **16.4** | Build, test, archive and sign the app | It is the newest Xcode officially supported on this machine's macOS 15.7.5; Apple lists Xcode 16.4 as supporting macOS 15.3 through macOS 26.1 and shipping the macOS 15.5 SDK. Xcode 26.x requires macOS 26 and is therefore not a usable build dependency here. | HIGH |
| Swift | **6 language mode**, Swift **6.1 compiler** from Xcode 16.4 | Native app and UI state | SwiftUI is Apple's preferred stack for new apps; Swift 6 mode gives compile-time concurrency checking. Do not install a separate Swift.org toolchain for the Xcode app. | HIGH |
| SwiftUI + AppKit bridges | macOS 15 SDK; **deployment target macOS 15.0**, arm64 only | Window chrome, dashboard, table, detail view, drag/drop, file panels, settings, confirmation UI | Native controls, accessibility, keyboard behavior, tables, menus and file dialogs fit the professional desktop requirement without shipping Chromium. Use AppKit only for a concrete macOS capability SwiftUI cannot express cleanly. | HIGH |
| Security.framework Keychain Services | system framework | Store DeepSeek API key | Apple explicitly recommends Keychain Services for small secrets. Store the key as a generic-password item; never write it to SQLite, logs, environment variables or command arguments. | HIGH |

**UI rule:** Swift owns presentation and user interaction only. It does not read decrypted WeChat databases, call DeepSeek, generate Excel, or hold send lifecycle state. It renders typed snapshots/events returned by the Go core. This prevents two competing sources of truth.

### Core Service and Data Plane

| Technology | Pinned version | Purpose | Why this choice | Confidence |
|---|---|---|---|---|
| Go | **1.26.5** | Long-lived local core service | Current supported patch release on the research date. The upstream Chatlog module already targets Go 1.25 and implements account discovery, decryption, WAL/incremental reads, history access, native send models and Excel export in Go. Go is the correct owner for business rules, persistence, background work and process orchestration. | HIGH |
| `github.com/mattn/go-sqlite3` | **v1.14.32** | App-owned SQLite access and reuse of upstream Chatlog database code | This is the version pinned by the inspected Chatlog Alpha commit. Reusing it avoids introducing a second SQLite driver and preserves known CGO behavior on arm64. Build with `CGO_ENABLED=1`, `GOOS=darwin`, `GOARCH=arm64`. | HIGH |
| `github.com/xuri/excelize/v2` | **v2.11.0** | `.xlsx` customer activation and send-result export | Current release, pure Go, already pinned upstream, supports styles, tables, filters, frozen panes and streaming writes. It removes any need for pandas/openpyxl or an Office installation. | HIGH |
| `encoding/json`, `net/http`, `crypto/sha256`, `database/sql` | Go 1.26 standard library | Typed DeepSeek transport, hash gates, storage | The protocol surface is small. Standard-library code makes timeouts, response limits, error classes and usage accounting explicit and avoids an SDK's model-name lag. | HIGH |

Do **not** copy Chatlog's Gin web console or HTTP debug UI. Extract the required Go packages into the product core. The final app has no browser-facing server. Swift launches exactly one core process and talks to it through a private Unix-domain socket using length-prefixed JSON messages. The socket lives in the app's Application Support directory with user-only permissions and an unguessable per-launch handshake token passed over inherited stdin, not on the command line.

### Native WeChat Instrumentation

| Technology | Pinned version / profile | Purpose | Why this choice | Confidence |
|---|---|---|---|---|
| CPython | **3.13.14 arm64**, bundled | Host the narrow Frida worker | A bundled runtime makes the product independent of `/usr/bin/python3` and user-installed packages. The current machine's Python 3.9.6 remains useful for reproducing the validated spike but is end-of-life and must not become the shipped runtime. | MEDIUM until the bundled worker repeats attach/send/cleanup tests |
| Frida Python bindings | **16.7.19** | Attach to WeChat, load the native sender agent and receive lifecycle events | This exact version is already proven locally against WeChat and its `cp37-abi3` arm64 wheel supports modern Python 3. Frida 17.x is not an automatic upgrade: changing it requires repeating the exact profile, send, Ack and cleanup matrix. | HIGH for the validated local combination; MEDIUM after rebundling |
| Frida GumJS / JavaScript agent | version supplied by Frida 16.7.19 | Hooks, native calls, object allocation and Ack observation inside WeChat | This is the established Frida architecture: the host attaches and injects a QuickJS agent; host/agent events are JSON-serializable. Keep agents prebuilt and immutable inside the signed bundle. | HIGH |
| PyInstaller | **6.21.0**, `onedir`, arm64 | Freeze the Python worker and Frida binding | Current stable release supports macOS and modern Python. `onedir` avoids runtime extraction and gives deterministic nested-code signing. Do not use UPX; PyInstaller documents that UPX-processed dylibs fail macOS code-sign validation on Apple Silicon. | MEDIUM until signed artifact validation |
| WeChat native profile | **4.1.11.55**, build **269111**, arm64; full dylib SHA-256 `c2a4794b343625a8013752095e76bc688acd42d48f30001a255620db2fc542a9`; arm64 slice SHA-256 `da53625065d283d748f959627f5e4d724eb786f2911f49c91a72cc12f17d30f7` | Fail-closed gate for key extraction and sending | These are the latest locally verified project facts. `REQUIREMENTS.md` and `questions.md` still mention 4.1.11.54; that is documentation drift, not a second supported profile. | HIGH |

**Native worker rule:** Python owns exactly one Frida `DeviceManager → Session → Script` generation at a time and processes commands serially. Go owns the durable queue but never issues a second native command until the worker returns one terminal event. Swift never talks to Frida directly.

The worker protocol must expose explicit `preflight`, `load`, `send`, `cancel`, `release`, and `health` commands and typed events for `queued`, `running`, protocol/Ack evidence, `succeeded`, `failed`, `cleanup_started`, and `cleanup_finished`. A successful `MMStartTask` call is not success. For every type, success requires its validated serializer/upload callback and corresponding response/Ack endpoint.

Use native `calloc`/`mmap` for every object WeChat may retain asynchronously. Do not continue the invalidated `uploadappattach -> sendappmsg` file path. Video and file remain separate adapters built from the validated Chatlog text/image lifecycle and `StartC2CUpload` callback model.

### DeepSeek Integration

| Setting | Required value | Rationale | Confidence |
|---|---|---|---|
| API format | OpenAI-compatible `POST {baseURL}/chat/completions` | Officially supported; implement directly in Go rather than importing the OpenAI SDK. | HIGH |
| Default base URL | `https://api.deepseek.com` | Official OpenAI-compatible endpoint. Allow an explicitly configured base URL, but validate HTTPS and show it in settings. | HIGH |
| Default model | **`deepseek-v4-flash`** | Current low-cost model for structured, non-reasoning extraction. The legacy `deepseek-chat` and `deepseek-reasoner` aliases retire on 2026-07-24 and must not appear in defaults or tests. | HIGH |
| Thinking | `{"type":"disabled"}` | V4 defaults to thinking mode; this workload requires predictable structured extraction, so non-thinking must be explicit. | HIGH |
| Response mode | `response_format: {"type":"json_object"}` | Official JSON Output mode. The prompt must contain the word JSON and an exact output example; set an explicit output limit. | HIGH |
| Validation | Decode into versioned Go structs; reject unknown/missing fields, out-of-range scores, blank content, truncated output, nonexistent evidence IDs and invented business facts | JSON Output guarantees valid JSON, not the project's semantic schema. An empty response is documented as possible and is a failed analysis, not a retry into another model. | HIGH |
| Usage | Persist `prompt_tokens`, `completion_tokens`, `prompt_cache_hit_tokens`, `prompt_cache_miss_tokens` and the model/base URL used | Required for actual cost display and audit. Do not estimate completed-run cost from character counts. | HIGH |
| Cache layout | Stable system prompt and store policy first; candidate evidence and per-contact request last | DeepSeek cache matches repeated prefixes and reports cache hit/miss token fields. | HIGH |

Use one bounded analysis worker pool in Go, independent from the single native-send queue. Network errors, HTTP status errors, malformed payloads, blank output and semantic-validation errors remain distinct terminal results. Do not silently switch model, base URL, thinking mode or provider.

### Local SQLite Design

Use **two data domains**, never one ambiguous database:

1. **WeChat source data:** owned by the extracted Chatlog data layer. Decryption and incremental synchronization preserve the SQLite database together with its `-wal`/`-shm` state. The product reads normalized contacts, sessions and history; the UI never sees raw tables or SQL.
2. **Product database:** one app-owned SQLite file under `~/Library/Application Support/<bundle-id>/agent.sqlite3` containing accounts, sync runs, conversations, deterministic facts, evidence excerpts, analysis runs, token usage, message drafts, attachments, send jobs, per-recipient attempts, Ack evidence and cleanup results.

Required connection policy:

- Enable `PRAGMA journal_mode=WAL`, `foreign_keys=ON` and a finite `busy_timeout` on every connection.
- Use one serialized writer and a small bounded read pool. Do not let Swift and Python open this database.
- Wrap each sync batch, analysis result and send-state transition in a transaction.
- Store schema migrations as embedded, monotonic SQL files and reject a database newer than the binary's schema version.
- Use stable IDs and unique constraints for `(account_id, conversation_id, source_message_id)` so incremental sync is idempotent.
- Store evidence by immutable source-message identity plus excerpt/hash; never accept a model-generated quote as source evidence.
- Treat the WAL file as part of persistent state during copy/backup. SQLite's official documentation warns that separating a database from its WAL can lose committed transactions or corrupt the copy.

Do not use SwiftData/Core Data, an ORM, PostgreSQL, Redis or a vector database. They create duplicate state, servers or migration layers without solving a first-version requirement.

### Excel Export

Generate the workbook in Go with Excelize v2.11.0. The first release should contain one customer activation table and one run metadata sheet:

- Auto-filterable Excel table, frozen header, explicit column widths, wrapped evidence/action text, date/score/status formats and a restrained style.
- Stable columns for contact, intent band/score, latest contact, deterministic facts, evidence, obstacle, suggested action, final draft and send result.
- Metadata sheet containing account display identifier, analysis range, run ID, model, token usage, export time and schema version; never include API keys or raw unselected chat history.
- Write to a temporary file in the destination directory, close/flush, reopen for a structural check, then atomically rename to the chosen `.xlsx` path. A failed export leaves no file presented as complete.

Excelize's stream writer is available for large sheets, but approximately 1,000 leads do not justify it initially. Use normal mode so tables/styles remain simple; add streaming only after measured memory pressure, because Excelize forbids mixing normal and stream writes on the same sheet.

## Process and Language Boundaries

```text
SwiftUI app (UI, Keychain, file picker)
  └─ private UDS, typed request/event protocol
      Go core (business rules, Chatlog extraction, SQLite, DeepSeek, XLSX, durable queues)
        └─ inherited pipes, one command at a time
            bundled Python worker (Frida session owner)
              └─ one immutable GumJS agent generation
                  WeChat 4.1.11.55 native process
```

| Boundary | Allowed data | Forbidden data |
|---|---|---|
| Swift ↔ Go | Typed view models, commands, progress, validated errors; API key only over an in-memory request when needed | SQL, database keys, Frida offsets, raw native logs |
| Go ↔ Python | Exact profile, one validated recipient command, staged attachment path, deadline/cancel command, typed native lifecycle events | DeepSeek key, whole customer database, UI state |
| Go ↔ DeepSeek | Store policy plus locally selected minimum evidence and stable opaque evidence IDs | Full six-month chat corpus, database key, local paths, native diagnostics |

The Go process is the application session coordinator. If it exits, Swift marks active work interrupted and does not infer success. If the Python worker exits, the current send fails, Go performs targeted generation cleanup/WeChat health verification, and no further send starts until a fresh preflight passes. This is explicit recovery of the same path, not a fallback transport.

## Packaging and Distribution

| Item | Decision | Confidence |
|---|---|---|
| App shape | One arm64 `.app`; Swift executable in `Contents/MacOS`, Go core and frozen Python worker as signed nested helpers, immutable scripts/profiles in resources | HIGH |
| Distribution | Direct Developer ID distribution, **not Mac App Store**; DMG or signed installer package | HIGH because process attachment and the project's SIP prerequisite conflict with a normal sandboxed-store product |
| Signing | Sign nested dylibs/extensions/helpers inside-out, then the app with Developer ID + Hardened Runtime + secure timestamp | HIGH |
| Notarization | Submit with `notarytool`, staple ticket, verify with `codesign --verify --deep --strict`, `spctl -a -vv`, and `stapler validate` | HIGH for Apple workflow; MEDIUM for Frida payload acceptance until exercised |
| Runtime prerequisite | UI performs a deterministic SIP/WeChat/profile/hash/permission preflight and blocks key extraction/sending with the exact failed check | HIGH |

Apple requires valid Developer ID signatures, Hardened Runtime and secure timestamps for notarization. The release phase must prove that the bundled Frida worker still attaches and cleans up after signing/notarization; notarization success alone does not prove native sending works.

Current workspace fact: only Command Line Tools are selected; full Xcode is not installed. Installing and selecting Xcode 16.4 is therefore an implementation prerequisite, not an optional fallback.

## Testing Stack and Release Gates

| Layer | Tool | Required coverage |
|---|---|---|
| Swift unit/integration | Swift Testing from Xcode 16.4 | View-model mapping, settings validation, Keychain adapter, IPC framing, cancellation and error presentation |
| macOS UI | XCTest/XCUIAutomation | Account connection flow, analysis range, table filter/sort, evidence detail, drag/drop, preview/confirmation, export save panel, cancellation |
| Go | `go test`, `go test -race`, table/golden tests | Private-chat filtering, deterministic extraction, idempotent sync, migrations, evidence binding, DeepSeek request/response validation, cost accounting, Excel structure, queue state machine |
| Python worker | `pytest` pinned in the lock file plus captured protocol fixtures | Profile parsing, hashes, command validation, event state machine, timeout/cancel/release paths; Frida calls abstracted only for unit tests |
| Cross-process | Real packaged helpers | Socket/pipe framing, crash handling, exact binary/resource lookup, no secrets in argv/env/logs |
| Native acceptance | Dedicated real Apple Silicon Mac, real WeChat 4.1.11.55 profile and test account | Text/image/video/file each require receiver-visible delivery, type-correct content, corresponding Ack, cancellation, cleanup and post-task WeChat health |
| Release | Archived, signed, notarized `.app` installed on a clean user account | Gatekeeper launch, key extraction preflight, six-month analysis, `.xlsx` open/filter, 100-target sequential send, no wrong recipient, helper leak, sustained high CPU or login loss |

Tests may use fixtures for speed, but fixtures cannot release a native sending capability. Video/file UI remains absent until its dedicated live gate passes. Run the 100-target test against the exact packaged artifact, not source scripts.

## Technologies Not to Use

| Do not use | Reason |
|---|---|
| Electron, Tauri, React, Vue, Qt/PySide | The product requires a native desktop panel; these add a web/bridge runtime or make Python own UI state while SwiftUI already covers the one supported platform. |
| A local Gin/FastAPI server or browser UI | Recreates the Chatlog web console that the product explicitly removes and exposes a larger local attack surface. Use private UDS IPC. |
| SwiftData/Core Data as a second store | Splits business state between Swift and Go and creates synchronization bugs. SQLite in Go is the single product truth. |
| OpenAI Python/Go SDK | The needed API is one stable HTTP endpoint; direct typed Go transport is smaller and prevents stale model aliases or hidden retries. |
| pandas/openpyxl | Excelize already exists in the Go core and covers the required workbook; another runtime and object model are unnecessary. |
| PostgreSQL, Redis, Elasticsearch, vector databases, RAG frameworks | No server or semantic retrieval requirement exists for approximately 1,000 local contacts. Deterministic SQL and selected evidence are enough. |
| Mac App Store sandbox | Process attachment, local WeChat access and the SIP-disabled prerequisite are incompatible with the intended operating model. |
| Universal binaries, Rosetta or Intel conditionals | The first release is Apple Silicon only. Extra architecture branches are untested surface. |
| Frida 17.x without a new validation matrix | The project has only verified 16.7.19. A version bump can change host/GumJS/session behavior and must not ride along with product work. |
| System `/usr/bin/python3` or user `pip` environment | The current system Python 3.9.6 caused an actual Frida compatibility issue and cannot provide deterministic customer installs. Bundle the worker. |
| `uploadappattach -> sendappmsg` for files | Spike 001 disproved this path on the exact 4.1.11.55 build: it reached `MMStartTask` but not `Req2Buf`/serializer/`Buf2Resp`. Remove it; do not comment it out or retain it as compatibility code. |
| Hermes, Share Sheet, clipboard, Accessibility/key simulation | These are different transports without the required native Ack and are explicitly forbidden fallbacks. |

## Installation / Build Baseline

These are the versions the implementation should encode in toolchain files and lock files:

```bash
# Build host prerequisite: install full Xcode 16.4, then select it.
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer

# Go core (download official Go 1.26.5 arm64 package first).
go mod init <project-module>
go get github.com/mattn/go-sqlite3@v1.14.32
go get github.com/xuri/excelize/v2@v2.11.0

# Native worker in a project-local build venv created from bundled-build Python 3.13.14.
python3.13 -m venv .venv-native
.venv-native/bin/python -m pip install --require-hashes -r native/requirements-build.txt
# requirements-build.txt pins frida==16.7.19, pyinstaller==6.21.0 and the chosen pytest patch.
```

Do not execute install commands from the app at customer runtime. All non-system dependencies ship signed inside the application.

## Known Gaps and Phase Research Flags

1. **Signed Frida bundle gate — MEDIUM confidence.** Build the frozen Python 3.13.14/Frida 16.7.19 worker immediately, sign/notarize an app skeleton and repeat attach/detach before broad UI work. This verifies packaging without inventing another transport.
2. **Native video and file adapters — LOW confidence until Spikes 002/003 pass.** The stack and boundaries are clear, but exact upload objects/callbacks/Ack points remain phase-specific reverse-engineering work. Neither capability may appear in release UI early.
3. **Requirements version drift — HIGH confidence.** Update the source-of-truth requirement from 4.1.11.54 to the verified 4.1.11.55 profile during roadmap/spec reconciliation. Do not support both.
4. **CPython rebundle — MEDIUM confidence.** Frida 16.7.19 publishes a macOS arm64 `cp37-abi3` wheel, but the production gate must still verify attach/send/cleanup under bundled Python 3.13.14 because only system Python 3.9.6 has been exercised locally so far.

## Sources

### Official platform and language sources

- Apple, [Xcode support matrix](https://developer.apple.com/support/xcode/) — Xcode 16.4 host compatibility, SDK and Swift 6.1 compiler. **HIGH**
- Apple, [Xcode 16.4 release notes](https://developer.apple.com/documentation/xcode-release-notes/xcode-16_4-release-notes) — macOS 15.5 SDK and host requirement. **HIGH**
- Apple, [SwiftUI apps](https://developer.apple.com/documentation/technologyoverviews/swiftui) — preferred framework for new Apple-platform apps. **HIGH**
- Apple, [Testing](https://developer.apple.com/documentation/xcode/testing) — Swift Testing for unit/integration and XCTest for UI tests. **HIGH**
- Apple, [Keychain Services](https://developer.apple.com/documentation/security/keychain-services) — encrypted storage for small secrets. **HIGH**
- Apple, [Notarizing macOS software before distribution](https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution) — Developer ID, Hardened Runtime, timestamp, `notarytool` and stapling workflow. **HIGH**
- Go project, [Go release history](https://go.dev/doc/devel/release) — Go 1.26.5 released 2026-07-07 and support policy. **HIGH**

### Official / primary dependency sources

- Chatlog Alpha commit `0ae63779ed8b50dff04f2483bb8c9d306953fc8a`, [`go.mod`](https://github.com/teest114514/chatlog_alpha/blob/0ae63779ed8b50dff04f2483bb8c9d306953fc8a/go.mod) — Go 1.25, `mattn/go-sqlite3` v1.14.32 and Excelize v2.11.0 pins. **HIGH**
- SQLite, [Write-Ahead Logging](https://sqlite.org/wal.html) — WAL concurrency and requirement to preserve the WAL with the database. **HIGH**
- Excelize, [official documentation](https://xuri.me/excelize/) and [streaming write](https://xuri.me/excelize/en/stream.html) — v2.11.0 requirements, features and stream-mode constraints. **HIGH**
- Frida, [installation](https://frida.re/docs/installation/), [JavaScript API](https://frida.re/docs/javascript-api/) and [C/core API](https://frida.re/docs/c-api/) — Python host, injected JavaScript, message/RPC and session model. **HIGH**
- PyPI, [Frida 16.7.19 files](https://pypi.org/project/frida/16.7.19/) — macOS 11+ arm64 `cp37-abi3` wheel. **HIGH**
- PyInstaller, [6.21 usage documentation](https://pyinstaller.org/en/stable/usage.html) — macOS packaging and UPX/code-sign restriction. **HIGH**

### Official DeepSeek sources

- DeepSeek, [first API call](https://api-docs.deepseek.com/quick_start/pricing-details-usd/) and [models/pricing](https://api-docs.deepseek.com/quick_start/pricing) — endpoint, current V4 model names and legacy alias retirement. **HIGH**
- DeepSeek, [Create Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion) — explicit `thinking.type=disabled` and response format. **HIGH**
- DeepSeek, [JSON Output](https://api-docs.deepseek.com/guides/json_mode/) — JSON mode requirements and documented empty-content possibility. **HIGH**
- DeepSeek, [Context Caching](https://api-docs.deepseek.com/guides/kv_cache/) — prefix matching and cache hit/miss usage fields. **HIGH**

### Project primary evidence

- `.planning/PROJECT.md`, `.planning/notes/chatlog-infrastructure-decisions.md`, `Agent.md`, `.planning/spikes/CONVENTIONS.md`, `.planning/spikes/MANIFEST.md`, and Spike 001 README/results — exact local WeChat profile, native-memory requirement, invalidated file path and lifecycle gates. **HIGH**

