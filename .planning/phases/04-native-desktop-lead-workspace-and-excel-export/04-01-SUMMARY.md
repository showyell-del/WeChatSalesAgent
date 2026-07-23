# Phase 4 Summary

- Replaced the Phase 0 placeholder window with a native AppKit merchant workspace; no WebView or local Web server is present.
- Added one `workspace.v1` snapshot that binds dashboard, table, detail, evidence, drafts, token usage, and costs to one published analysis run.
- Added native search and intent-band filtering, evidence-backed customer detail, editable activation copy, and an Excel export action.
- Added a real `.xlsx` workbook with an overview sheet, filterable activation table, typed dates/numbers, formulas, conditional formatting, frozen panes, and editable send status.
- Added fail-closed behavior when the current account has no published DeepSeek analysis.
- Local UI and workbook fixture validation passed; the real current account remains gated by its missing published DeepSeek run.
