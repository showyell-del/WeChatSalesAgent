# Phase 1: Account, Key, and Consistent Sync Foundation - Context

**Gathered:** 2026-07-23
**Status:** Ready for implementation
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

Users can select one verified WeChat account and produce a fresh local, account-bound data generation from the currently running Chatlog service. This phase establishes account discovery, explicit key/read/sync status, local SQLite product state, staging generation, atomic publish, and failure classes that do not present stale data as current.

This phase does not implement lead scoring, DeepSeek analysis, Excel export, final desktop UI, video/file sending, or batch outreach.

</domain>

<decisions>
## Implementation Decisions

### Data source
- **D-01:** Use Chatlog HTTP as the verified Phase 1 data source because `/health`, `/api/v1/db`, and `/api/v1/sessions` are live and return the current local account data.
- **D-02:** Do not expose Chatlog's generic database pages in the product.
- **D-03:** Do not parse raw decrypted databases directly in Phase 1 unless Chatlog service becomes unavailable and a new verified direct-reader plan is created.

### Account identity
- **D-04:** Derive account identity from database paths under `xwechat_files/{account_id}/db_storage`.
- **D-05:** A sync run binds to exactly one selected `account_id`.
- **D-06:** Multiple discovered accounts can exist in product state, but only one account can be active for a generation.

### Freshness and failure
- **D-07:** Sync writes to a staging generation first and publishes only after health, db list, account derivation, and sessions fetch all pass.
- **D-08:** Failed sync must leave the previous published generation marked old; it must never label old data as latest.
- **D-09:** Missing Chatlog service, missing account path, no sessions, key-required state, and HTTP parse failures must have distinct terminal codes.

### the agent's Discretion
- The local module layout, SQLite schema details, CLI command names, and JSON event schema are at the agent's discretion as long as they are simple, testable, and directly support later lead analysis.

</decisions>

<specifics>
## Specific Ideas

- Build a small Python core first because Python 3.9.6 is verified locally and Go is not installed.
- Product state lives in a local SQLite file under an ignored runtime directory.
- Every sync emits JSONL diagnostics so the future desktop app can surface exact failure steps.

</specifics>

<canonical_refs>
## Canonical References

### Product and requirements
- `.planning/PROJECT.md` - Core value, no-fallback rules, and product boundary.
- `.planning/REQUIREMENTS.md` - REQ-DATA-001 through REQ-DATA-005.
- `.planning/ROADMAP.md` - Phase 1 goal and success criteria.
- `.planning/STATE.md` - Current project state and Phase 0 gates.

### Verified infrastructure
- `Agent.md` - Verified Chatlog commands/API and current local toolchain facts.
- `.planning/phases/00-commercial-delivery-and-exact-profile-gate/00-VERIFICATION.md` - Phase 0 gate status.
- `chatlog_2f54920_darwin_arm64/README.md` - Installed Chatlog Alpha behavior.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/phase0_chatlog_smoke.sh` proves Chatlog binary and HTTP service paths.
- `native-worker/phase0_worker.py` establishes the JSONL diagnostic convention.

### Established Patterns
- Scripts use `set -euo pipefail`.
- Diagnostics use `step`, `status`, `code`, `message`, and `evidence`.
- Generated runtime output belongs under ignored local directories, not git.

### Integration Points
- Future desktop app can shell out to or embed the Phase 1 CLI commands.
- Future Phase 2 reads the published generation and session rows.

</code_context>

<deferred>
## Deferred Ideas

- Full message history corpus and deterministic extraction - Phase 2.
- DeepSeek analysis and cost ledger - Phase 3.
- User-facing account selection UI - Phase 4.
- Native send queue integration - Phase 6.

</deferred>

---

*Phase: 01-account-key-and-consistent-sync-foundation*
*Context gathered: 2026-07-23*
