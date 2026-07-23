# Phase 3 Summary

The strict DeepSeek analysis pipeline is implemented locally. It uses direct HTTPS, `deepseek-v4-flash` by default, non-thinking JSON mode, Pydantic strict validation, deterministic evidence membership checks, commercial-truth checks, and one provider attempt per candidate per run.

The current published corpus produces 130 locally selected candidates after one under-14-data exclusion. At the configured reference prices and maximum output bound, the conservative estimate is USD `0.09594522`; provider-reported usage remains the only source of actual cost.

Eighteen tests pass, including a complete mocked request-to-published-lead run. A real DeepSeek run is intentionally not published because no API Key is installed and external personal-data transfer is not approved in the example profile.
