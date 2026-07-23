# Phase 3 Context

## Locked decisions

- Provider is DeepSeek through its OpenAI-compatible HTTPS API.
- Keep the implementation linear and explicit. This is structured classification/generation, not a multi-agent workflow and not RAG.
- Use only locally selected evidence excerpts from the published Phase 2 corpus.
- Strict JSON schema validation is mandatory; malformed or unsupported output fails and is never repaired automatically.
- The user configures API Key, Base URL, model, token pricing, and business truth. Default model is `deepseek-v4-flash` as specified by the product requirements, but the interface must surface provider rejection exactly.
- Score label is `成交意向分`, never statistical conversion probability before calibration with real outcomes.
- Drafts are generated only for final actionable candidates and must not invent claims, prices, discounts, inventory, or customer needs.
- Persist prompt/schema/model versions and exact provider usage fields for every call.
