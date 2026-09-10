import json
from typing import Dict

from .ai_cli import DEEPSEEK_KEYCHAIN_SERVICE
from .ai_models import BusinessProfile
from .analysis_store import AnalysisStore
from .deepseek_client import DeepSeekClient
from .keychain import KeychainStore


class DashboardSummaryError(RuntimeError):
    pass


def generate_dashboard_summary(db: str, payload: Dict, timeout: int = 120) -> str:
    store = AnalysisStore(db)
    try:
        config = store.config()
    finally:
        store.close()
    profile = BusinessProfile.model_validate(config["business_profile"])
    if not profile.external_api_data_transfer_approved:
        raise DashboardSummaryError("AI_EXTERNAL_TRANSFER_NOT_APPROVED")
    api_key = KeychainStore(DEEPSEEK_KEYCHAIN_SERVICE).get("default")
    if not api_key:
        raise DashboardSummaryError("DEEPSEEK_API_KEY_MISSING")
    response = DeepSeekClient(api_key, config["base_url"], timeout=timeout).complete_json(
        config["model"],
        [
            {
                "role": "system",
                "content": "You summarize aggregate WeChat activity for a business operator. Return JSON only: {\"summary\":\"concise Chinese summary with trends, active groups, topics and actionable observations\"}.",
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
        ],
        min(1200, int(config["max_tokens"])),
    )
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise DashboardSummaryError("DEEPSEEK_CHOICES_INVALID")
    content = choices[0].get("message", {}).get("content")
    try:
        parsed = json.loads(content)
    except (TypeError, json.JSONDecodeError) as exc:
        raise DashboardSummaryError("DEEPSEEK_OUTPUT_NOT_JSON") from exc
    summary = parsed.get("summary") if isinstance(parsed, dict) else None
    if not isinstance(summary, str) or not summary.strip():
        raise DashboardSummaryError("DEEPSEEK_SUMMARY_EMPTY")
    return summary.strip()
