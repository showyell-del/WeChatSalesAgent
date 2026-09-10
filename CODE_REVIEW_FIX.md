---
status: all_fixed
findings_in_scope: 22
fixed: 22
skipped: 0
iteration: 1
fixed_at: 2026-07-30T10:18:43Z
review_path: CODE_REVIEW.md
---

# Full Repository Code Review Fix Report

All 5 Critical and 17 Warning findings were fixed. No finding was skipped. Per the worktree-safety instruction, fixes were not staged or committed and deleted `.planning/` artifacts were not touched.

## Fixed issues

### CR-01: Minor-data transfer gate

Deterministic positive and uncertain child indicators now inspect actual candidate evidence, including child terms, school-stage terms, and ages 1-17. The decision, indicators, and evidence IDs are stored in `minor_screenings`; positive and uncertain packets are excluded unless explicitly approved. Evidence: `test_child_semantics_without_age_or_grade_is_screened_and_stored`.

### CR-02: Explicit recipient authorization

Explicit IDs now only narrow the actionable `高意向/待激活` set. Unknown or non-actionable requested IDs reject the entire request with `SEND_RECIPIENTS_UNAUTHORIZED` and the rejected IDs. Evidence: `test_explicit_customer_ids_cannot_bypass_actionable_bands`.

### CR-03: Native-session close cleanup

Close now unconditionally terminates, waits, kills, and reaps the worker when graceful detach times out; only PPID-matching Frida helpers are terminated and verified gone before temporary-directory deletion. Evidence: `test_native_close_timeout_forces_worker_reap_before_error`.

### CR-04: Native service identity

Daemon readiness now binds nonce, canonical DB path, start timestamp, owner App PID, current WeChat PID, and daemon PID. App and CLI verify live process commands/current WeChat ownership; commands and results carry the nonce and identity is rechecked during waits. Evidence: `test_stale_ready_pid_without_exact_identity_is_rejected` and Objective-C syntax validation.

### CR-05: Full Chatlog validation

Unavailable `chatlog http list` now emits `failed` and exits nonzero. Full validation additionally asserts the positive callable-service event before success. Evidence: `test_full_chatlog_smoke_fails_closed` and shell syntax validation.

### WR-01: Provider model audit

Missing or unequal provider models now fail with `DEEPSEEK_MODEL_MISMATCH` before success persistence. Evidence: `test_provider_model_mismatch_fails_run`.

### WR-02: Wrapped timeouts

`URLError(reason=socket.timeout)` now maps to `DEEPSEEK_TIMEOUT`, matching bare timeouts. Evidence: `test_wrapped_transport_timeout_is_typed` and `test_transport_timeout_is_typed`.

### WR-03: Staging run finalization

Every post-creation exception is converted to a typed analysis failure and guarded run finalization preserves recorded call cost. Evidence: `test_unexpected_persistence_error_finalizes_staging_run`.

### WR-04: Latest send status ordering

Recipient queue timestamps use nanoseconds and latest status selects exactly one row with `ROW_NUMBER()` ordered by queue time, batch creation, and batch ID. Evidence: `test_same_timestamp_latest_status_has_one_deterministic_winner`.

### WR-05: Service-start duplicate batches

The App verifies/starts the native service before creating the confirmed batch, so service startup failure cannot leave a queued batch. Evidence: `test_service_is_started_before_batch_creation_in_app` and Objective-C syntax validation.

### WR-06: Partial cancellation

Batch aggregation now exposes `cancelled`, uses `partially_cancelled` when success and cancellation coexist, and never labels `succeeded < total` as full success. Evidence: `test_partial_cancellation_is_not_reported_as_success`.

### WR-07: ACK durability

Native `ret=0` first commits `send_ack_journal` plus non-retryable `delivery_unknown_after_ack`, then transactionally reconciles recipient and batch success. Startup and daemon recovery reconcile journals before interruption handling. Evidence: `test_ack_journal_reconciles_confirmed_delivery` and `test_dispatch_uses_native_receipt_for_every_recipient`.

### WR-08: Single native profile truth

`native-worker/profiles/4.1.12.28.json` now contains the verified offsets and instruction windows. Both Python gates load it and Python injects it into JS; JS contains no parallel numeric offsets. Evidence: `test_active_send_profile_matches_packaged_wechat_profile` and Node syntax validation.

### WR-09: Broken native probe

`native-worker/send/native_probe.py` was removed. The active sender contains its exact WeChat PID lookup and no missing probe/profile resources remain. Evidence: `test_native_probe_is_removed`.

### WR-10: Exact Pydantic packaging

The build manifest and verifier require Pydantic 2.12.5 and pydantic-core 2.41.5 before copy; the built App and mounted DMG checks assert both exact versions. Evidence: `test_build_manifest_is_exact_and_fail_closed` and live manifest verification.

### WR-11: Chatlog license

The build copies `chatlog/LICENSE` beside the binary and mounted-DMG validation requires it. Evidence: `test_chatlog_license_and_release_cleanup_are_required`.

### WR-12: Sync data root preservation

The caller derives and stores `data_root` before key/decompression work, so failure status updates retain the discovered root. Evidence: `test_sync_failure_preserves_discovered_data_root`.

### WR-13: Malformed daemon commands

JSON parsing, exact-field validation, nonce validation, batch recovery, and terminal `.failed` writing are inside the per-command recovery boundary; malformed commands cannot terminate the service loop. Evidence: `test_daemon_rejects_malformed_commands_inside_recovery_boundary`.

### WR-14: Workbook send statuses

Backend and workbook now consume the same `agent_core/send_statuses.json`, including blocked, sending, partial cancellation, and ACK-unknown states. Evidence: `test_workbook_statuses_share_canonical_mapping` and Node syntax validation.

### WR-15: Isolated Phase 4 negative fixture

The hardcoded live account check was replaced by a temporary SQLite missing-analysis fixture. Evidence: `test_phase4_negative_case_uses_isolated_fixture`.

### WR-16: Release intermediate cleanup

After successful mounted-DMG verification and hash/size collection, `build_dmg.sh` removes the exact intermediate `APP_DIR`. Evidence: `test_chatlog_license_and_release_cleanup_are_required`.

### WR-17: Exact project build inputs

`config/build_inputs.json` is the project-owned source of exact Node/tool/Python package identities. Builds require explicit locked source directories and fail closed through `scripts/verify_build_inputs.py`; Codex-cache/user-site defaults were removed. Live verification matched Node v24.14.0 SHA-256 `20a18709f0154d668f1bd6f6ea8c2a7ae001447b4b2c339732f22e57a8767a55` and artifact-tool 2.8.33 package hash `91d9db7d61e1c26f96eb1cfb9f62274b58bf4f4155a7b16874b973ac7cd2bc18`.

## Verification

- `python3 -m unittest discover -s Tests -p 'test_*.py' -v`: 56 passed, including localhost HTTP tests.
- Python compile: passed for `agent_core`, native worker/sender, and build-input verifier.
- Node syntax: passed for native sender and workbook builder.
- `bash -n scripts/*.sh`: passed.
- Objective-C `clang -fsyntax-only`: passed.
- Exact build-input manifest verification: passed.
- `git diff --check`: passed.
- DMG rebuild/release: intentionally not run; reserved for orchestrator final package validation.

Logic/state-machine fixes require final human/package acceptance on the authorized environment, especially native daemon ownership and real `filehelper` ACK behavior.

---

_Fixed: 2026-07-30T10:18:43Z_  
_Fixer: Codex (gsd-code-fixer)_  
_Iteration: 1_

## Iteration 2: cross-layer hardening and package verification

The independent second pass fixed additional issues beyond the original 22 findings:

- ACK durability is split into a first committed non-retryable receipt journal transaction and a separate reconciliation transaction.
- Analysis finalization failures are surfaced as typed terminal failures instead of being hidden by the original exception.
- Native result files, daemon readiness, canonical DB identity, launch nonce, owner App PID, WeChat PID, and command/result nonce are validated as one identity chain.
- Exact build inputs now cover full dependency trees, not only package entry files; DMG replacement is atomic after candidate verification.
- WeChat `4.1.12.29/269341` has an exact hash-gated profile. Profile selection is exact and contains no version fallback.
- Native cleanup now uses `shutdown hooks -> script.unload -> exact owned helper termination -> WeChat health check`; the hanging Frida `session.detach()` path is absent from normal cleanup.
- Native dispatch waits until a completed natural `default StartTask` has been observed. The text fake object is attached only to the matching task-local node and its callback/destructor paths are skipped explicitly; manager shared slots are not modified.

Verification after iteration 2:

- 63 unit tests passed.
- Phase 0 quick validation and no-fallback scan passed.
- Phase 4 AppKit workspace, deterministic snapshot, preview rendering, and real XLSX export passed.
- Phase 6 state machine and dispatch integration passed.
- Python compile, Node syntax, all shell syntax, exact build-input verification, and `git diff --check` passed.
- Final DMG mounted read-only and passed signing, bundled dependency, license, manifest, and AppKit smoke checks.
- DMG: SHA-256 `6b89bb6d858dcb14b16e5b5f7e6dc0467043b007082f0ee0af5c808ff631e2d9`, 132,060,779 bytes.

The final `4.1.12.29` packaged `filehelper` receipt gate could not be certified. Iteration 3 therefore removed the entire native-send capability and all related profiles instead of shipping pending functionality.

## Iteration 3: unsafe native send removed

The pending native-send path was not certifiable. A live WeChat `4.1.12.29/269341` run crashed in `mars::stn` with `EXC_BAD_ACCESS` and an explicit possible pointer-authentication failure after the internal `StartTask` call reached a Frida-allocated fake C++ object/vtable. Offset changes and additional cleanup cannot make unsigned function pointers valid across this arm64e boundary.

Per the project no-fallback rule, the capability was removed instead of hidden or replaced:

- Removed the App send button, batch editor, preview, daemon startup, and shutdown logic.
- Removed `native_send_session`, send CLI/daemon/dispatch/store/status mapping, NativeWorker, profiles, Frida sender, Phase 6 scripts, and send tests.
- Removed send status from workspace snapshots and Excel output.
- Removed NativeWorker from the packaged App and added regression/no-fallback assertions preventing its return.
- Retained Frida only as a locked Chatlog key-extraction dependency; the App no longer attaches to WeChat itself.

Final verification after removal: 62 unit tests, Phase 0 quick, no-fallback scan, Phase 4 AppKit/UI/XLSX, Ruff, Python compileall, Node syntax, Shell syntax, Objective-C syntax, and `git diff --check` passed. The final DMG was mounted read-only and verified to contain no NativeWorker or send modules.

DMG SHA-256: `bbd12eecf5779b249a288b0ca71075dcdaac919f0c20424c1e5bdca68284b14a`; size: 131,731,279 bytes.
