# Phase 4 Verification

status: passed_local
verified_at: 2026-07-23

## Automated evidence

- Workspace unit tests verify one-run metrics/evidence consistency and fail-closed missing-analysis behavior.
- Objective-C/AppKit compilation and `--ui-smoke` load a two-lead published fixture into KPI cards, table, and detail view.
- `--render-preview` produces a visually inspected native workspace PNG with readable light appearance and evidence-backed detail.
- The spreadsheet runtime exports a real XLSX, inspects KPI formulas, scans formula errors, and renders both sheets for visual inspection.
- The end-to-end export wrapper reads the same SQLite fixture snapshot and publishes a valid XLSX archive.
- WebView/local-Web-server scan passes.

## External gate

The real account has no published DeepSeek run because the API key and external transfer approval are not configured. The real workspace therefore correctly displays an analysis-not-ready state rather than fixture or stale lead data.
