# Project Agent Notes

## Chatlog Alpha

- The project contains the macOS Apple Silicon Chatlog Alpha app at `chatlog_2f54920_darwin_arm64/`; it is an application, not a Codex skill.
- Verified commands: `./chatlog_2f54920_darwin_arm64/chatlog-darwin-arm64 --help`, `key --help`, `http --help`, and `action --help` all run successfully.
- Normal local flow: run `start-chatlog.command` (or the binary), use the TUI to select the account, obtain database keys, decrypt data, then start the HTTP service. Browse locally at `http://127.0.0.1:5030/`.
- On macOS its database-key extraction requires `frida-tools` in the current user's Python environment and requires SIP to be disabled; do not run Chatlog, Python/Frida, or WeChat with `sudo`.
- The system `python3` is 3.9.6. The current Frida 17.x package is incompatible because it imports `typing.NotRequired`, which Python 3.9 does not provide. Use `frida==16.7.19` for this interpreter.
- Verified after installation: `python3` imports Frida 16.7.19 and can attach to and detach from the running WeChat main process. The next `chatlog key` run will restart WeChat to capture and validate the database key.
- Verified Chatlog data API: `GET /api/v1/sessions?format=json&limit=5000` returns the full session list; filter `is_group=false` and exclude official/service usernames for human private-chat candidates.
- Verified private history API: `GET /api/v1/history?chat=<username>&time=<date-range>&limit=<n>&offset=<n>&format=json` returns message sender, timestamp, content, type, and media fields. Use this API for batch lead analysis rather than raw database search.
- For sales-lead screening, preserve evidence excerpts for every score, extract contact details deterministically, and output only actionable private-chat leads. Do not treat a score as a statistical purchase probability unless it has been calibrated against real conversion labels.

## Native sender extraction

- The upstream native sender at commit `2f54920d` supports only `text` and `image`; its request normalization rejects other message types.
- Reusable sender components are `internal/wechat/send/model.go`, `runner_darwin.go`, `assets/native_send_once.py`, `assets/native_send_image_once.py`, `assets/native/single_send_agent.js`, and `assets/native/image_send_agent.js`. Reuse the serialized job/command/release semantics from `internal/chatlog/http/send_debug.go`, not its debug HTTP UI.
- Video and arbitrary-file sending do not have a native WeChat implementation. The Hermes bridge methods are an external adapter and are not a replacement. Each new native type requires its own upload entry and callbacks, protobuf/task payload, CDN metadata mapping, serializer compatibility, ack-safe cleanup, and live verification.
- Production sending must fail closed on an exact WeChat version and dylib hash, own one serialized native session, reject unsupported types explicitly, and verify cleanup without retry or compatibility fallbacks.
- Local WeChat 4.1.11.55 verified profile facts: build `269111`; full `wechat.dylib` SHA-256 `c2a4794b343625a8013752095e76bc688acd42d48f30001a255620db2fc542a9`; arm64 slice SHA-256 `da53625065d283d748f959627f5e4d724eb786f2911f49c91a72cc12f17d30f7`.
- Verified 4.1.11.55 send offsets: `MMStartTask=0x5121478`, default manager wrapper `0x51173d0`, `Req2Buf=0x3e5930c`, serializer hook `0x3e5938c`, post-serializer `0x3e59394`, `AutoBufferWrite=0x3e7ff18`, `Buf2Resp=0x3e7eaf0`.
- Native sender objects that WeChat may hold asynchronously must be allocated from native memory (`calloc`/`mmap`), not ordinary Frida heap. Frida heap objects allowed `MMStartTask` to return but produced bad `x1` state and dirty unload behavior.
- The `wechat_chatter` simple file path (`uploadappattach` chunks then `sendappmsg` appmsg type 6) is not a valid 4.1.11.55 first implementation path in this environment: both `uploadappattach` and direct `sendappmsg` file tasks reached `MMStartTask` with the correct task id but never reached `Req2Buf` or `Buf2Resp`.
- After a native send attempt times out, `script.unload()` and `session.detach()` can also time out; the clean recovery path is controlled WeChat restart plus targeted cleanup of only the current Frida helper. Do not leave a hot-unload-only lifecycle for file/video send experiments.

## Phase 0 local delivery facts

- Verified local toolchain on 2026-07-23: `/usr/bin/clang` can compile an Objective-C/AppKit native app; `python3` is 3.9.6; `python3` imports Frida 16.7.19.
- Swift is not currently usable for Phase 0 on this machine: SwiftPM manifest linking fails against PackageDescription, and direct `swiftc` fails because the compiler patch version does not match the installed macOS SDK Swift interfaces. Do not use `swift test` or `swift build` until the Command Line Tools/Xcode toolchain is repaired.
- `codesign`, `notarytool`, and `stapler` are available through Command Line Tools, but `security find-identity -v -p codesigning` reports `0 valid identities found`; Developer ID signing/notarization must fail closed until a valid identity and credentials are installed.
- `go` is not currently available on PATH and was not found at `/opt/homebrew/bin/go` or `/usr/local/go/bin/go`; Phase 0 plans must not require a Go build step.
- Latest process probe did not show a running WeChat main process; Phase 0 profile checks must report `WECHAT_NOT_RUNNING` distinctly from profile mismatch and worker failures.
- Verified WeChat disk dylib location on 2026-07-23: `/Applications/WeChat.app/Contents/Resources/wechat.dylib`; full SHA-256 and arm64 slice SHA-256 match the certified values above.
- Source reference snapshots are still available at `/tmp/chatlog-alpha-spike.WWc9fK/repo` commit `2f54920d4aa78e1812819f77bb59a5e380c6f0ec` and `/tmp/wechat-chatter-spike` commit `49114827bc83f8381eb638e8a56f3f0305fc1a1c`.

## Phase 0 verified commands

- `scripts/build_phase0_app.sh` builds `dist/phase0/WeChatSalesAgent.app`, ad-hoc signs it, and reports `DEVELOPER_ID_IDENTITY_MISSING` when no Developer ID identity is installed.
- `dist/phase0/WeChatSalesAgent.app/Contents/MacOS/WeChatSalesAgent --smoke` emits `PHASE0_APP_LAUNCHED`.
- `python3 native-worker/phase0_worker.py version` reports Frida `16.7.19`.
- `python3 native-worker/phase0_worker.py profile-gate` reports `WECHAT_NOT_RUNNING` when WeChat is not running; with WeChat running it must validate build `269111`, full dylib SHA-256, and arm64 slice SHA-256 before native operations.
- `scripts/phase0_chatlog_smoke.sh --help-smoke` reports `CHATLOG_HELP_CALLABLE`.
- `scripts/phase0_validate.sh --quick` passes the AppKit build/sign and no-fallback scan.
- `scripts/phase0_validate.sh --full` passes local automated gates and may include explicit blocked gates for missing Developer ID identity, WeChat not running, and manual `filehelper` text-send smoke.
- `DEVELOPER_ID_IDENTITY_MISSING`, `WECHAT_NOT_RUNNING`, and `TEXT_SEND_SMOKE_MANUAL_REQUIRED` are not fallback success states; they are terminal gates that must be resolved before claiming commercial Phase 0 completion.

## Phase 1 verified account and sync path

- `scripts/phase1_sync.sh accounts` reads Chatlog's running and historical accounts through the JSON Lines action interface without exposing the database key.
- `scripts/phase1_sync.sh switch --account-id wxid_3prysbeqgvci22_9f8d` verified historical-account selection for the current business account.
- `scripts/phase1_sync.sh connect --account-id wxid_3prysbeqgvci22_9f8d` verifies a 64-hex database key, stores and reads it back from macOS Keychain service `com.wechat-sales-agent.database-key`, runs first/incremental decrypt, and validates 11 primary session/contact/message databases as readable SQLite files.
- Chatlog's `security add-generic-password -w` prompt form does not read a secret from piped stdin in this non-interactive runtime; it created an empty item and was removed. The verified CLI form passes the value explicitly. Replace that transport with Security.framework when the native desktop target owns Keychain access.
- `scripts/phase1_sync.sh sync --account-id wxid_3prysbeqgvci22_9f8d --limit 5000` verified an account-bound staged generation containing 1,202 sessions. Publishing a later generation atomically marks the prior published generation `old`; a failed staging generation leaves the prior published generation unchanged.
- `scripts/phase1_validate.sh` runs unit tests, Python compilation, Chatlog health, account discovery, account switch, key/decrypted-database verification, live decrypt/sync, and state readback. Runtime state is written only to ignored `runtime/agent_state.sqlite3`.

## Phase 2 verified private-chat corpus path

- Use `since` and `until` epoch seconds for `/api/v1/history`; the `time=YYYY-MM-DD~YYYY-MM-DD` form is not a verified range for this build.
- Read each conversation twice with `is_self=false` and `is_self=true`. The API returns an accurate direction-specific `total_count` when that filter is present; page until the fetched count equals it. Do not infer sender direction from display names.
- `scripts/phase2_corpus.sh --account-id wxid_3prysbeqgvci22_9f8d --days 183 --page-size 500` completed a full, non-sampled run over 1,202 sessions: 244 bidirectional private conversations were eligible, 958 were excluded, and 47,479 immutable evidence references were published.
- Static exclusions are explicit: group chat, `gh_` official account, known system holder, and named service entry. Remaining conversations require at least one inbound and one outbound non-system text message in range.
- Evidence IDs bind account, source generation, conversation, local message ID, direction, sender, timestamp, and content SHA-256. Evidence bodies are globally deduplicated; `corpus_evidence` maps immutable evidence into each corpus rebuild.
- Deterministic facts are extracted only from inbound evidence. The verified published corpus contains 739 fact references across phone, landline, age, grade, region, budget, available time, obstacle, and dance-specific explicit need fields.
- Broad generic region/time/course patterns produced false positives and were removed. Current region extraction uses known administrative names or explicit address context; available-time extraction requires a time expression paired with availability or visit/class intent; explicit need is dance-specific.
- `scripts/phase2_validate.sh` verifies unit tests, Python compilation, full corpus/session count equality, account/generation scope, content hashes, reconstructed evidence IDs, direction rules, fact foreign keys, and absence of eligible conversations without evidence.

## Phase 3 verified DeepSeek API contract

- Use one direct OpenAI-compatible `POST <base-url>/chat/completions` request with bearer authorization. The official API currently accepts `deepseek-v4-flash`; send the user-configured model unchanged and surface provider rejection instead of substituting another model.
- DeepSeek JSON Output requires `response_format={"type":"json_object"}`, an explicit JSON instruction/example in the prompt, and a bounded `max_tokens`. The provider documents occasional empty content; in this project empty, malformed, truncated, filtered, or resource-interrupted output is a terminal failure with zero retry and zero repair.
- JSON validity is not business-schema validity. Validate once with Pydantic 2.12.5 using strict types and `extra="forbid"`, then check customer/timestamp equality and every evidence reference against the exact sent packet before persistence.
- Accept only `finish_reason="stop"`. Actual cost uses provider-returned cache-hit input, cache-miss input, and completion token counts with configured per-million `Decimal` prices; missing or inconsistent usage must never be replaced by a local estimate.
- `scripts/phase3_ai.sh configure --business-file config/business_profile.example.json` saves validated non-secret DeepSeek/business settings; API keys are read from environment only during configuration and round-trip through Keychain service `com.wechat-sales-agent.deepseek-api-key`.
- `scripts/phase3_ai.sh estimate --account-id wxid_3prysbeqgvci22_9f8d` completes in under one second after the set-based candidate-query fix. The verified current example profile selects 130 of 244 eligible conversations, locally excludes one under-14-data case, and reports a conservative maximum estimate of 321,323 input tokens, 182,000 output tokens, and USD `0.09594522` at the configured July 23, 2026 reference prices.
- Required fact evidence is selected deterministically before recent context. Whole selected records must fit the 18-evidence/7,000-character packet bounds; required evidence overflow fails with `AI_CONTEXT_TOO_LARGE` rather than truncating, summarizing, or dropping facts.
- `scripts/phase3_validate.sh` passes 18 tests, including one-call mock transport, strict JSON/schema rejection, evidence membership, forbidden claims, exact usage/cost arithmetic, atomic result+ledger persistence, full mocked analysis publication, live candidate selection, and cost estimation.
- The current machine has no DeepSeek API Key in the product Keychain; `scripts/phase3_ai.sh run ...` reports `DEEPSEEK_API_KEY_MISSING` and makes no provider call. The example profile also keeps `external_api_data_transfer_approved=false` and `minor_data_approved=false` until the operator explicitly confirms those gates.

## Phase 4 verified native workspace and export path

- `agent_core.workspace_service.load_snapshot` is the only read model for the dashboard, customer table, evidence detail, drafts, token counts, costs, and Excel export. It accepts only one published analysis run and fails with `PUBLISHED_ANALYSIS_MISSING` instead of showing corpus candidates as analyzed leads.
- `app/Phase0App/main.m` is now the native AppKit merchant workspace. It contains no WebView or local Web server and supports KPI cards, customer/need/contact search, intention-band filtering, evidence detail, and editable activation copy.
- Force the app to `NSAppearanceNameAqua` and explicitly set table/text-view backgrounds. Without this, a dark macOS appearance produces black embedded table and text surfaces inside the light workspace.
- An `NSTextView` used as an `NSScrollView.documentView` needs a non-zero initial frame, vertical resizing, and `textContainer.widthTracksTextView=YES`; a zero-frame text view rendered blank even though its string was populated.
- `scripts/phase4_export.sh` uses the bundled spreadsheet runtime and `@oai/artifact-tool` to publish a real filterable XLSX. Resolve the output path before changing into the temporary module directory or a relative export will be deleted with that directory.
- `scripts/phase4_validate.sh` verifies the native UI, visual PNG render, strict snapshot behavior, spreadsheet formulas, formula-error scan, visual sheet renders, XLSX archive, and end-to-end export wrapper.
