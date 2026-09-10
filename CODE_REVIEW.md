---
status: issues_found
reviewed: 2026-07-30T09:50:26Z
depth: deep
scope: full_current_worktree
files_reviewed: 62
files_reviewed_list:
  - .gitignore
  - AGENTS.md
  - Agent.md
  - README.md
  - Tests/test_phase1_sync.py
  - Tests/test_phase2_corpus.py
  - Tests/test_phase3_ai.py
  - Tests/test_phase4_workspace.py
  - Tests/test_phase6_send.py
  - agent_core/__init__.py
  - agent_core/ai_cli.py
  - agent_core/ai_models.py
  - agent_core/ai_prompt.py
  - agent_core/analysis_engine.py
  - agent_core/analysis_store.py
  - agent_core/chatlog_client.py
  - agent_core/chatlog_runtime.py
  - agent_core/corpus_builder.py
  - agent_core/corpus_cli.py
  - agent_core/corpus_store.py
  - agent_core/corpus_validate.py
  - agent_core/deepseek_client.py
  - agent_core/events.py
  - agent_core/extractors.py
  - agent_core/keychain.py
  - agent_core/native_send_session.py
  - agent_core/send_cli.py
  - agent_core/send_daemon.py
  - agent_core/send_dispatch.py
  - agent_core/send_store.py
  - agent_core/sync_cli.py
  - agent_core/sync_store.py
  - agent_core/workspace_cli.py
  - agent_core/workspace_service.py
  - app/Phase0App/Info.plist
  - app/Phase0App/main.m
  - chatlog/LICENSE
  - config/business_profile.example.json
  - native-worker/phase0_worker.py
  - native-worker/probes/attach_smoke.js
  - native-worker/profiles/4.1.12.28.json
  - native-worker/send/native/single_send_agent.js
  - native-worker/send/native_probe.py
  - native-worker/send/native_send_once.py
  - requirements.txt
  - scripts/build_dmg.sh
  - scripts/build_lead_workbook.mjs
  - scripts/build_phase0_app.sh
  - scripts/phase0_chatlog_smoke.sh
  - scripts/phase0_validate.sh
  - scripts/phase0_worker.sh
  - scripts/phase1_sync.sh
  - scripts/phase1_validate.sh
  - scripts/phase2_corpus.sh
  - scripts/phase2_validate.sh
  - scripts/phase3_ai.sh
  - scripts/phase3_validate.sh
  - scripts/phase4_export.sh
  - scripts/phase4_validate.sh
  - scripts/phase4_workspace.sh
  - scripts/phase6_send.sh
  - scripts/phase6_validate.sh
findings:
  critical: 5
  warning: 17
  info: 0
  total: 22
---

# Full Repository Deep Code Review (Historical)

> Superseded by `CODE_REVIEW_FINAL.md`. Native WeChat sending reviewed below was removed completely on 2026-08-01 after live arm64e pointer-authentication crashes; it is not part of the current product or package.

## Scope and method

Reviewed the complete current working tree as the source of truth, including all uncommitted source, tests, configuration, scripts, project guidance, and the Chatlog license. The embedded `chatlog/chatlog-darwin-arm64` binary, `dist/`, generated caches, and deleted `.planning/` artifacts were excluded from source review; the Chatlog binary's current type, executable bit, size, and SHA-256 were checked only as packaging provenance. Existing user changes and deletions were left untouched.

The review traced these contracts end to end:

- AppKit UI actions and lifecycle → bundled Python CLIs → SQLite schemas and published-state transitions.
- Chatlog process/action calls → localhost HTTP pagination → account/generation/corpus/evidence identity.
- DeepSeek configuration and approval → request envelope → strict JSON/schema/evidence validation → token/cost ledger publication.
- Send preview and recipient selection → batch state machine → daemon command directory → persistent Frida worker → native JS hooks → parsed `BaseResponse.ret=0` receipt.
- Source/runtime/package dependency and profile consistency, validation scripts, and no-fallback/no-degradation constraints.

## Critical issues

### CR-01: The minor-data gate uploads clearly child-related conversations unless an age or grade regex happens to match

**Files:** `agent_core/analysis_store.py:178-191`, `agent_core/extractors.py:8-9`, `agent_core/extractors.py:47-50`, `app/Phase0App/main.m:704-706`

**Issue:** When `minor_data_approved` is false, candidate exclusion checks only extracted `age` and `grade` facts. A conversation such as `我家孩子想体验少儿街舞` produces an `explicit_need` fact but no `age`/`grade`, so it remains a candidate and its evidence is sent to DeepSeek after the general transfer approval. The UI explicitly offers `少儿街舞课` and describes the checkbox as approval for clearly identified minor evidence, so this is a privacy/authorization bypass rather than an ambiguous product case. Ages outside the narrow regex (for example `2岁`) have the same problem.

**Fix:** Make minor screening a fail-closed pre-transfer classifier over the actual evidence, with deterministic child indicators (`孩子`, `儿童`, `少儿`, `幼儿`, school-stage terms, all plausible minor ages) in addition to structured facts. Store the screening decision and evidence, and exclude any positive/uncertain child-related packet unless `minor_data_approved` is true. Add tests using child semantics without explicit age/grade.

### CR-02: Explicit customer IDs bypass the actionable-band authorization gate

**Files:** `agent_core/send_store.py:127-135`, `agent_core/send_cli.py:127-132`

**Issue:** `create_batch()` enforces `高意向/待激活` only when no explicit IDs are supplied. With `customer_ids`, every matching published lead is selected regardless of `intent_band`. A direct reproduction changed a lead to `排除`, called `create_batch(..., customer_ids=[that_id])`, and received a queued recipient. The CLI exposes `--customer-id`, so this is reachable without modifying the database schema or native worker and violates the product rule that only actionable leads may be sent.

**Fix:** Always require `lead["intent_band"] in ACTIONABLE_BANDS`; explicit IDs must only narrow that authorized set. Reject the whole request with a typed error listing any requested non-actionable or unknown IDs rather than silently dropping them.

### CR-03: A native-session close timeout discards its control directory without terminating or reaping the worker

**File:** `agent_core/native_send_session.py:174-198`

**Issue:** `close()` writes the release marker and waits, but on timeout it immediately raises. `__exit__()` then closes the log and deletes the temporary directory; it never terminates/kills/waits for the still-running worker and never performs PPID-scoped helper cleanup. The worker can therefore retain its Frida session/hooks after the App believes cleanup completed, block the next attach, or continue against paths that were just deleted. This directly contradicts the documented single-owner and cleanup guarantees.

**Fix:** Put process reaping in an unconditional cleanup path. After the graceful deadline, terminate, wait, then kill and wait if necessary; collect only helpers whose PPID is the worker PID, terminate those helpers, and verify they are gone before deleting the directory. Preserve the close error only after cleanup has completed.

### CR-04: The App trusts any live PID in a stale `ready.json` as the native send daemon

**Files:** `app/Phase0App/main.m:146-153`, `agent_core/send_cli.py:59-94`, `agent_core/send_daemon.py:60-63`

**Issue:** The App accepts `status=ready` plus `kill(pid, 0)` and does not verify process identity, parent/task ownership, database path, current WeChat PID, or a launch nonce. If a stale PID has been reused by an unrelated process, `ensureNativeSendService` returns success. `send_cli` performs the same file-only readiness check, writes a command nobody consumes, and waits for up to 3600 seconds. A stale daemon tied to a previous WeChat process/database is also accepted.

**Fix:** Write a per-launch nonce, canonical DB path, daemon start time, owner App PID, and WeChat PID into `ready.json`; verify all fields plus the live process command before reuse. Have CLI include/verify the nonce in command and result files and fail promptly if the daemon PID/WeChat PID exits or readiness changes while waiting.

### CR-05: The advertised full validation passes when the Chatlog HTTP service is unavailable

**Files:** `scripts/phase0_chatlog_smoke.sh:25-30`, `scripts/phase0_validate.sh:34-50`

**Issue:** `--http-list-smoke` emits a `blocked` event but exits zero when `chatlog http list` fails. Because `phase0_validate.sh --full` runs under `set -e`, that zero status allows it to continue and print `PHASE0_FULL_PASSED`. A delivery with no usable Chatlog HTTP service can therefore pass the full gate, violating both the no-fallback rule and the real-completion meaning of full validation.

**Fix:** Emit `failed`, return nonzero from the unavailable branch, and make the full validator assert a positive callable-service event before reporting success. If an environment-only check is desired, give it a distinct command that cannot be confused with full acceptance.

## Warnings

### WR-01: DeepSeek responses are published even when the provider reports a different model

**File:** `agent_core/analysis_engine.py:164-178`

**Issue:** The response model is recorded but never compared with `config["model"]`. A gateway/provider response from another model is accepted, displayed under the configured model, and costed with the configured model's price table. This breaks the model and exact-cost audit contract.

**Fix:** Reject missing or unequal `response["model"]` with a typed `DEEPSEEK_MODEL_MISMATCH` before storing a success; normalize only explicitly documented provider aliases.

### WR-02: Wrapped socket timeouts are misclassified as generic unavailability

**Files:** `agent_core/deepseek_client.py:42-54`, `Tests/test_phase3_ai.py:95-98`

**Issue:** `urllib` commonly raises `URLError(reason=socket.timeout)`. The earlier `except URLError` maps that to `DEEPSEEK_UNAVAILABLE`, so the later timeout handler never sees it. A direct mocked `URLError(socket.timeout(...))` reproduction returned `DEEPSEEK_UNAVAILABLE`. The current test only raises bare `socket.timeout` and misses the real wrapper.

**Fix:** In the `URLError` branch, inspect `exc.reason` and map timeout reasons to `DEEPSEEK_TIMEOUT`; add both wrapped and bare timeout tests.

### WR-03: Unexpected database/runtime errors can leave analysis runs permanently in `staging`

**Files:** `agent_core/analysis_engine.py:147-218`, `agent_core/ai_cli.py:110-125`

**Issue:** Once `create_run()` commits, only `AnalysisError` and Pydantic `ValidationError` reach `fail_run()`. SQLite errors, serialization errors, or other unexpected failures during call/result persistence or publication escape without finalizing the run; `command_run` also does not catch general SQLite exceptions. The API call may already have incurred cost while the durable ledger remains `staging` with `actual_cost_usd=0`.

**Fix:** After `run_id` exists, finalize every exception path in a guarded `except Exception` block, preserving the original error and any recorded call cost. Emit a typed CLI failure and add a test that injects `sqlite3.OperationalError` after run creation.

### WR-04: Latest send status is nondeterministic when batches share the same second

**File:** `agent_core/send_store.py:311-330`

**Issue:** `queued_at` has one-second resolution. The subquery selects `max(queued_at)` and joins only on customer and timestamp, so two batches created in the same second both match. The final dictionary silently keeps whichever row SQLite happens to return last. A reproduction created queued and blocked batches for one customer with identical timestamps and produced two matching rows.

**Fix:** Add a monotonic/tie-breaking key (for example nanosecond timestamp plus batch ID), or select exactly one row using `ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY queued_at DESC, created_at DESC, batch_id DESC)`.

### WR-05: A service-start failure leaves the confirmed batch queued and retries create duplicates

**Files:** `app/Phase0App/main.m:889-910`, `agent_core/send_store.py:115-161`

**Issue:** The App creates and commits the batch before starting/verifying the native service. If startup fails, it returns without cancelling or blocking that batch. Workspace status becomes `已排队`; pressing send again creates another batch for the same recipients and text.

**Fix:** Start/verify the service before creating the batch, or atomically block/cancel the just-created batch with the startup failure code before returning. Add an App/service integration test for this branch.

### WR-06: Partially cancelled batches are labeled fully succeeded

**File:** `agent_core/send_store.py:81-113`

**Issue:** When some recipients are `cancelled` and all remaining recipients succeed, none of the earlier branches match and the batch becomes `succeeded`, even though `succeeded < total`. The UI label `发送成功` therefore overstates the native-send result.

**Fix:** Introduce a terminal partial/cancelled status or define success as `succeeded == total`; expose succeeded/cancelled totals explicitly.

### WR-07: A receipt can be accepted by WeChat but recorded as blocked, making retries duplicate the message

**Files:** `agent_core/send_dispatch.py:14-23`, `agent_core/send_store.py:258-271`

**Issue:** `session.send_text()` returns only after `BaseResponse.ret=0`, but the following SQLite `finish_recipient(..., True, ...)` can fail. The daemon catches the exception and blocks the still-`sending` recipient as an internal failure. The durable state then invites a retry even though WeChat already accepted the text.

**Fix:** Distinguish `delivery_unknown_after_ack` from a confirmed send failure and never present it as safely retryable. Persist an ACK journal record before broader batch aggregation, and reconcile it transactionally on restart.

### WR-08: The packaged profile JSON disagrees with the active sender and is not used by runtime gates

**Files:** `native-worker/profiles/4.1.12.28.json:7-17`, `native-worker/send/native/single_send_agent.js:5-12`, `native-worker/send/native_send_once.py:53-66`, `Agent.md:32-36`

**Issue:** The profile says `req2buf_exit=0x3faa684` and `buf2resp=0x3fcec84`, while the active verified hooks and Agent notes use `0x3faa678` and `0x3fcec78`; serializer addresses/labels also differ. The sender and gate hardcode their own values and never read the packaged profile. The file is copied into the App and a test named `active_send_profile` checks only version/hashes, so it falsely appears authoritative.

**Fix:** Keep one exact profile as the runtime source of truth, load it in both gate and sender, validate every hook offset/instruction, and test all consumed values. Remove obsolete offsets rather than preserving parallel profiles.

### WR-09: The packaged native probe is nonfunctional because all of its default resources are missing

**File:** `native-worker/send/native_probe.py:17-32`, `scripts/build_phase0_app.sh:55-57`

**Issue:** The probe resolves `native/probe_agent.js` and `profiles/4.1.11.53.json` under `native-worker/send/`; neither file exists. Yet the complete `native-worker/send` directory is packaged. Running this shipped tool fails before inspection.

**Fix:** Since it is not part of the MVP runtime, remove it from the packaged/source send directory. If it remains a supported developer tool, point it to the actual profile/probe and add a callable smoke test.

### WR-10: The build does not enforce the pinned Pydantic version it claims to package

**Files:** `requirements.txt:2`, `scripts/build_phase0_app.sh:11-12`, `scripts/build_phase0_app.sh:74-78`, `scripts/build_phase0_app.sh:88-93`

**Issue:** Requirements pin `2.12.5`, but packaging copies whichever Pydantic is in the invoking user's site-packages and accepts any `2.x`. A later or earlier 2.x build can therefore be delivered despite the documented exact runtime, with no manifest proving the copied version.

**Fix:** Assert `pydantic.VERSION == "2.12.5"` and the matching core version before copying and again inside the built App; source packages from an immutable locked build environment.

### WR-11: The redistributed Chatlog binary omits its required license from the App/DMG

**Files:** `chatlog/LICENSE:1-20`, `scripts/build_phase0_app.sh:46-60`

**Issue:** The MIT license requires its notice to be included in copies/substantial portions, but the build copies only the Chatlog binary into `Resources/Chatlog`; the repository license is not copied into the distributable.

**Fix:** Copy `chatlog/LICENSE` beside the binary and add a DMG validation assertion for it.

### WR-12: A sync failure after account discovery overwrites the stored data root with an empty string

**Files:** `agent_core/sync_cli.py:92-111`, `agent_core/sync_cli.py:158-206`

**Issue:** `prepare_account()` stores the correct root before key/decompression verification, but assignment to the caller's `root` occurs only if the whole function returns. If it raises, the outer `root` remains `""`; the exception handler then upserts the account as failed using that empty value, destroying the discovered path and reducing diagnostic quality.

**Fix:** Derive/store the root in the caller before risky preparation, or update only status/error fields on failure without replacing `data_root`.

### WR-13: One malformed daemon command terminates the entire send service outside its recovery boundary

**File:** `agent_core/send_daemon.py:63-80`

**Issue:** JSON parsing and required-field extraction occur before the per-command `try`. A corrupt/stale command file raises out of the loop, tears down the native session, and leaves the command in place to fail again. This is especially hazardous in the stable service directory intended for reuse.

**Fix:** Move read/parse/field validation inside the command recovery block, atomically rename malformed commands to a terminal `.failed` result, and continue only after batch state is reconciled. Reject unknown fields and verify the daemon nonce.

### WR-14: Excel validation rejects two statuses the backend legitimately exports

**Files:** `agent_core/send_store.py:44-52`, `scripts/build_lead_workbook.mjs:71-96`

**Issue:** Workspace rows can contain `发送阻断` and `发送中`, but the workbook's send-status validation list contains only `未发送/已排队/发送成功/发送失败/已取消`. An export performed during sending or after a blocked batch therefore writes a value outside its own declared validation contract.

**Fix:** Generate the workbook list from the same canonical status mapping, including every projected value, and add export fixtures for blocked and sending recipients.

### WR-15: Phase 4 validation depends on a specific live account being absent

**File:** `scripts/phase4_validate.sh:37-42`

**Issue:** After completing its isolated fixture checks, the validator queries the repository runtime database for hardcoded account `wxid_3prysbeqgvci22_9f8d` and requires the command to fail with `PUBLISHED_ANALYSIS_MISSING`. If that account has valid local analysis, the validation gate fails. The result therefore depends on operator data rather than source correctness.

**Fix:** Remove the live-runtime assertion and create an explicit temporary missing-analysis fixture for the negative case.

### WR-16: DMG verification leaves the intermediate App that project policy requires removing

**Files:** `Agent.md:18`, `scripts/build_dmg.sh:7-45`, `scripts/build_phase0_app.sh:7-8`

**Issue:** The build creates `dist/WeChatSalesAgent.app`, verifies the DMG, and never removes the App. Project guidance says the intermediate App must be deleted after verification so the DMG remains the sole deliverable. Repeated release work can therefore expose or mistake the unpackaged intermediate for a supported artifact.

**Fix:** After successful mounted-DMG verification, remove the exact `APP_DIR`; retain it only behind an explicit developer build mode outside the release command.

### WR-17: The release build depends on an unpinned Codex-local Node/tool installation

**File:** `scripts/build_phase0_app.sh:13-15`, `scripts/build_phase0_app.sh:81-105`

**Issue:** By default, packaging reads Node and `@oai/artifact-tool` from `${HOME}/.cache/codex-runtimes/codex-primary-runtime` (or another mutable environment override), without checking a Node version, package version, or package hash. A non-Codex builder cannot reproduce the advertised standalone artifact, and different local tool versions can silently generate different workbook behavior.

**Fix:** Vendor or fetch from a lockfile-controlled build dependency set, assert exact Node/tool versions and hashes before copying, and record them in a release manifest. This is a build-time requirement only; do not add Codex as an end-user runtime dependency.

## Verified strengths

- The product remains DeepSeek-only: no Codex/WorkBuddy/external-agent CLI, export/publish protocol, or alternate AI-engine path was found.
- Native send success is not inferred from `MMStartTask` return or UI state. The active path matches the task ID, reads the Buf2Resp payload, parses `BaseResponse.ret`, and exposes `.done` only after a zero receipt.
- Chatlog history is fetched independently in both directions, paginated to reported totals, and rejects count loss; session pagination also detects a no-progress page.
- Account selection is explicit for multiple accounts, decrypted databases are opened read-only, and published generations/corpora/analyses replace previous versions transactionally rather than publishing partial staging data.
- DeepSeek output rejects extra judgment fields, non-JSON/empty content, non-`stop` completion, score/band mismatch, foreign evidence IDs, usage-total mismatch, forbidden claims, and unapproved numeric prices. No retry/repair/model fallback library or path was found.
- API keys and database keys use macOS Keychain; raw chat/evidence stays in the local SQLite database until explicit external-transfer approval.
- App send preview occurs before batch creation, uses the visible actionable set, and table selection does not inject a private per-customer AI draft into the batch text editor.
- Packaging verifies the exact Chatlog binary hash/architecture, exact Frida version, bundled Python import path, ad-hoc signature, mounted DMG, and AppKit smoke. The checked Chatlog binary is arm64, executable, 35,242,722 bytes, SHA-256 `bdafee95f7ceeecbcad2249f724df05865fb6b348ffb99b0694ebe735d4aef06`.
- The no-fallback static scan passed for the currently enumerated forbidden transport strings.

## Validation evidence

- `python3 -m unittest discover -s Tests -p 'test_*.py' -v`: **37 tests passed** when rerun with loopback binding allowed. The first sandboxed run had two `PermissionError` failures solely because the sandbox prohibited the tests' localhost HTTP server.
- `python3 -m py_compile agent_core/*.py native-worker/phase0_worker.py native-worker/send/*.py`: passed using a temporary bytecode cache.
- `node --check native-worker/send/native/single_send_agent.js`: passed.
- `bash -n scripts/*.sh`: passed.
- Objective-C `clang -fsyntax-only` for `app/Phase0App/main.m`: passed.
- `scripts/phase0_validate.sh --no-fallback-scan`: passed.
- `scripts/phase6_validate.sh`: passed (8 send-state tests).
- `scripts/phase4_validate.sh`: passed outside the sandbox (4 workspace tests, build/sign, AppKit UI smoke and render, real XLSX export, and `PHASE4_LOCAL_VALIDATION_OK`).
- The resulting current App was read-only compared with the mounted existing DMG: deep codesign verification passed, `diff -qr` reported no differences, both main binaries had SHA-256 beginning `965aa42`, packaged `agent_core`, native send code, and profiles matched source, and the DMG remained SHA-256 `68cf32bc37054e9523174076fa0ca0006cf9c561ff05924d65c74a5ae15b4b3b`, 131,744,869 bytes. The generated intermediate App was then removed in accordance with `Agent.md`.
- `git diff --check`: passed.
- Reproductions confirmed: child-related evidence with only an `explicit_need` fact remained a candidate while minor transfer was unapproved; explicit `排除` recipient selection; two same-second send-status rows; wrapped timeout reported as unavailable; missing native-probe resources.

The release script paths were reviewed without invoking `scripts/build_dmg.sh`; the phase 4 validation/build and read-only mounted-DMG comparison above were performed by the orchestrating review and cleaned up afterward. No live WeChat send, Chatlog key extraction, DeepSeek request, or external release operation was performed.

## Coverage gaps

- No test proves child-related evidence without an age/grade fact is excluded.
- No test proves explicit send IDs remain restricted to actionable bands.
- No test covers native worker close timeout, forced reaping, PPID-scoped helper cleanup, stale/PID-reused readiness, WeChat PID changes, or App termination during an active send.
- No test covers same-second send batches, partial cancellation, database failure after native ACK, queued-batch cleanup after service startup failure, or malformed/stale daemon commands.
- DeepSeek tests do not cover wrapped timeouts, provider-model mismatch, redirect behavior, or unexpected persistence errors after run creation.
- The profile test checks version/build/hashes but not any runtime hook offset or instruction.
- `phase0_validate.sh --full` was not run; it depends on live WeChat/Chatlog state and currently contains CR-05's false-positive branch.
- No automated assertion checks that the built App contains `chatlog/LICENSE` or exact Pydantic 2.12.5.
- No export test covers `发送阻断`/`发送中`, and Phase 4 validation still depends on a hardcoded live account being absent.
- No release assertion verifies intermediate App cleanup or exact Node/`@oai/artifact-tool` build versions.
- No current real packaged-runtime `filehelper` ACK acceptance was performed in this review.

---

_Reviewed: 2026-07-30T09:50:26Z_  
_Reviewer: Codex (gsd-code-reviewer)_  
_Depth: deep_
