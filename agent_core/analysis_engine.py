import hashlib
import json
import time
import uuid
from decimal import Decimal
from typing import Dict, Tuple

from pydantic import ValidationError

from .ai_models import (
    BusinessProfile,
    LeadJudgment,
    ProviderLeadJudgment,
    ProviderUsage,
)
from .ai_prompt import PROMPT_VERSION, SCHEMA_VERSION, build_messages, prompt_sha256
from .analysis_store import AnalysisStore
from .deepseek_client import DeepSeekClient, DeepSeekError


SELECTOR_VERSION = "evidence-selector-v1"


class AnalysisError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def estimate_tokens(value: str) -> int:
    byte_count = len(value.encode("utf-8"))
    return max(1, (byte_count + 2) // 3)


def cost_usd(usage: ProviderUsage, settings: Dict) -> Decimal:
    million = Decimal("1000000")
    return (
        Decimal(usage.prompt_cache_hit_tokens)
        * Decimal(settings["cache_hit_usd_per_million"])
        + Decimal(usage.prompt_cache_miss_tokens)
        * Decimal(settings["cache_miss_usd_per_million"])
        + Decimal(usage.completion_tokens) * Decimal(settings["output_usd_per_million"])
    ) / million


def validate_provider_response(
    response: Dict, customer_packet: Dict, business: BusinessProfile
) -> Tuple[LeadJudgment, ProviderUsage, Dict]:
    choices = response.get("choices")
    if (
        not isinstance(choices, list)
        or len(choices) != 1
        or not isinstance(choices[0], dict)
    ):
        raise AnalysisError(
            "DEEPSEEK_CHOICES_INVALID", "DeepSeek must return exactly one choice."
        )
    choice = choices[0]
    if choice.get("finish_reason") != "stop":
        raise AnalysisError(
            "DEEPSEEK_FINISH_NOT_STOP", "DeepSeek completion did not finish normally."
        )
    message = choice.get("message")
    if not isinstance(message, dict):
        raise AnalysisError(
            "DEEPSEEK_MESSAGE_INVALID", "DeepSeek choice message must be an object."
        )
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise AnalysisError(
            "DEEPSEEK_CONTENT_EMPTY", "DeepSeek returned empty content."
        )
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AnalysisError(
            "DEEPSEEK_OUTPUT_NOT_JSON", "DeepSeek content is not valid JSON."
        ) from exc
    try:
        provider_judgment = ProviderLeadJudgment.model_validate(parsed)
        usage = ProviderUsage.model_validate(response.get("usage"))
    except ValidationError as exc:
        raise AnalysisError("DEEPSEEK_SCHEMA_INVALID", str(exc)) from exc

    expected_customer = customer_packet["customer_id"]
    expected_recent = customer_packet["recent_contact_ts"]
    available = {item["evidence_id"] for item in customer_packet["evidence"]}
    if provider_judgment.customer_id != expected_customer:
        raise AnalysisError(
            "CUSTOMER_ID_MISMATCH", "DeepSeek returned a different customer ID."
        )
    if provider_judgment.recent_contact_ts != expected_recent:
        raise AnalysisError(
            "RECENT_CONTACT_MISMATCH", "DeepSeek changed the recent contact timestamp."
        )
    if not set(provider_judgment.evidence_ids).issubset(available):
        raise AnalysisError(
            "EVIDENCE_ID_MISMATCH",
            "DeepSeek referenced evidence outside the supplied packet.",
        )
    controlled_draft = (
        "您好，想跟您确认一下，目前是否方便聊聊您的需求？"
        if provider_judgment.intent_band in ("高意向", "待激活")
        else None
    )
    judgment = LeadJudgment.model_validate(
        {
            **provider_judgment.model_dump(),
            "draft_text": controlled_draft,
            "draft_evidence_ids": list(provider_judgment.evidence_ids)
            if controlled_draft
            else [],
        }
    )
    return (
        judgment,
        usage,
        {"finish_reason": choice["finish_reason"], "content": content},
    )


def prepare_customer_packet(
    store: AnalysisStore, corpus_id: str, candidate: Dict
) -> Dict:
    try:
        packet = store.packet(corpus_id, candidate["username"])
    except RuntimeError as exc:
        if str(exc) == "AI_CONTEXT_TOO_LARGE":
            raise AnalysisError(
                "AI_CONTEXT_TOO_LARGE",
                "Required fact evidence exceeds the configured packet bounds.",
            ) from exc
        raise
    return {
        "customer_id": candidate["username"],
        "display_name": candidate["display_name"],
        "recent_contact_ts": candidate["latest_timestamp"],
        "facts": packet["facts"],
        "evidence": packet["evidence"],
    }


def estimate_run(store: AnalysisStore, account_id: str, limit: int = 0) -> Dict:
    config = store.config()
    business = BusinessProfile.model_validate(config["business_profile"])
    corpus = store.published_corpus(account_id)
    selection = store.candidates(
        corpus["corpus_id"], business.lead_keywords, business.minor_data_approved
    )
    candidates = selection["candidates"]
    if limit:
        candidates = candidates[:limit]
    input_tokens = 0
    for candidate in candidates:
        packet = prepare_customer_packet(store, corpus["corpus_id"], candidate)
        messages = build_messages(business.model_dump(), packet)
        input_tokens += estimate_tokens(
            json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
        )
    output_tokens = len(candidates) * int(config["max_tokens"])
    estimate = (
        Decimal(input_tokens) * Decimal(config["cache_miss_usd_per_million"])
        + Decimal(output_tokens) * Decimal(config["output_usd_per_million"])
    ) / Decimal("1000000")
    return {
        "corpus": corpus,
        "candidates": candidates,
        "privacy_excluded": selection["privacy_excluded"],
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "estimated_cost_usd": estimate,
    }


def run_analysis(
    db_path: str, account_id: str, api_key: str, limit: int = 0, timeout: int = 120
) -> Dict:
    store = AnalysisStore(db_path)
    run_id = ""
    try:
        config = store.config()
        business = BusinessProfile.model_validate(config["business_profile"])
        if not business.external_api_data_transfer_approved:
            raise AnalysisError(
                "AI_EXTERNAL_TRANSFER_NOT_APPROVED",
                "External API personal-data transfer has not been approved in business configuration.",
            )
        estimate = estimate_run(store, account_id, limit)
        candidates = estimate["candidates"]
        if not candidates:
            raise AnalysisError(
                "ANALYSIS_CANDIDATES_EMPTY",
                "Local evidence selection produced no candidates.",
            )
        metadata = {
            "model": config["model"],
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": prompt_sha256(),
            "schema_version": SCHEMA_VERSION,
            "config_snapshot": {
                key: value
                for key, value in config.items()
                if key not in ("setting_id", "updated_at")
            },
        }
        metadata["config_snapshot"]["selector_version"] = SELECTOR_VERSION
        run_id = store.create_run(
            estimate["corpus"]["corpus_id"],
            account_id,
            metadata,
            len(candidates),
            estimate["estimated_cost_usd"],
        )
        client = DeepSeekClient(api_key, config["base_url"], timeout)
        actual_cost = Decimal("0")
        for candidate in candidates:
            packet = prepare_customer_packet(
                store, estimate["corpus"]["corpus_id"], candidate
            )
            messages = build_messages(business.model_dump(), packet)
            request_material = {
                "model": config["model"],
                "messages": messages,
                "max_tokens": config["max_tokens"],
            }
            request_raw = json.dumps(
                request_material,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            request_hash = hashlib.sha256(request_raw.encode("utf-8")).hexdigest()
            estimated_call_tokens = estimate_tokens(request_raw)
            estimated_call_cost = (
                Decimal(estimated_call_tokens)
                * Decimal(config["cache_miss_usd_per_million"])
                + Decimal(config["max_tokens"])
                * Decimal(config["output_usd_per_million"])
            ) / Decimal("1000000")
            call_id = "call_" + uuid.uuid4().hex
            response = None
            try:
                response = client.complete_json(
                    config["model"], messages, int(config["max_tokens"])
                )
                provider_model = response.get("model")
                if (
                    not isinstance(provider_model, str)
                    or provider_model != config["model"]
                ):
                    raise AnalysisError(
                        "DEEPSEEK_MODEL_MISMATCH",
                        "DeepSeek returned a model different from the configured model.",
                    )
                judgment, usage, details = validate_provider_response(
                    response, packet, business
                )
                call_cost = cost_usd(usage, config)
                response_raw = json.dumps(
                    response, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                success_call = {
                    "call_id": call_id,
                    "run_id": run_id,
                    "username": candidate["username"],
                    "status": "succeeded",
                    "request_sha256": request_hash,
                    "provider_response_id": str(response.get("id", "")),
                    "provider_model": str(response.get("model", "")),
                    "system_fingerprint": str(response.get("system_fingerprint", "")),
                    "finish_reason": details["finish_reason"],
                    "prompt_tokens": usage.prompt_tokens,
                    "cache_hit_tokens": usage.prompt_cache_hit_tokens,
                    "cache_miss_tokens": usage.prompt_cache_miss_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                    "estimated_cost_usd": str(estimated_call_cost),
                    "usage_json": json.dumps(
                        response.get("usage"),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "actual_cost_usd": str(call_cost),
                    "response_sha256": hashlib.sha256(
                        response_raw.encode("utf-8")
                    ).hexdigest(),
                    "error_code": None,
                    "error_message": None,
                    "created_at": int(time.time()),
                }
                store.add_success(
                    success_call,
                    run_id,
                    candidate["username"],
                    candidate["display_name"],
                    judgment,
                    packet["facts"],
                )
                actual_cost += call_cost
            except (DeepSeekError, AnalysisError) as exc:
                failed_usage = None
                failed_cost = None
                response_hash = None
                if isinstance(response, dict):
                    try:
                        failed_usage = ProviderUsage.model_validate(
                            response.get("usage")
                        )
                        failed_cost = cost_usd(failed_usage, config)
                    except ValidationError:
                        failed_usage = None
                    response_raw = json.dumps(
                        response,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    response_hash = hashlib.sha256(
                        response_raw.encode("utf-8")
                    ).hexdigest()
                failed_choice = (
                    (response.get("choices") or [{}])[0]
                    if isinstance(response, dict)
                    and isinstance(response.get("choices"), list)
                    and response.get("choices")
                    else {}
                )
                if not isinstance(failed_choice, dict):
                    failed_choice = {}
                store.add_call(
                    {
                        "call_id": call_id,
                        "run_id": run_id,
                        "username": candidate["username"],
                        "status": "failed",
                        "request_sha256": request_hash,
                        "provider_response_id": str(response.get("id", ""))
                        if isinstance(response, dict)
                        else None,
                        "provider_model": str(response.get("model", ""))
                        if isinstance(response, dict)
                        else None,
                        "system_fingerprint": str(
                            response.get("system_fingerprint", "")
                        )
                        if isinstance(response, dict)
                        else None,
                        "finish_reason": failed_choice.get("finish_reason"),
                        "prompt_tokens": failed_usage.prompt_tokens
                        if failed_usage
                        else None,
                        "cache_hit_tokens": failed_usage.prompt_cache_hit_tokens
                        if failed_usage
                        else None,
                        "cache_miss_tokens": failed_usage.prompt_cache_miss_tokens
                        if failed_usage
                        else None,
                        "completion_tokens": failed_usage.completion_tokens
                        if failed_usage
                        else None,
                        "total_tokens": failed_usage.total_tokens
                        if failed_usage
                        else None,
                        "usage_json": json.dumps(
                            response.get("usage"),
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        if isinstance(response, dict)
                        and isinstance(response.get("usage"), dict)
                        else None,
                        "estimated_cost_usd": str(estimated_call_cost),
                        "actual_cost_usd": str(failed_cost)
                        if failed_cost is not None
                        else None,
                        "response_sha256": response_hash,
                        "error_code": exc.code,
                        "error_message": exc.message,
                        "created_at": int(time.time()),
                    }
                )
                raise AnalysisError(exc.code, exc.message) from exc
        store.publish_run(run_id, account_id)
        return {
            "run_id": run_id,
            "candidate_count": len(candidates),
            "estimated_cost_usd": str(estimate["estimated_cost_usd"]),
            "actual_cost_usd": str(actual_cost),
        }
    except Exception as exc:
        if isinstance(exc, AnalysisError):
            code, message = exc.code, exc.message
        elif isinstance(exc, ValidationError):
            code, message = "AI_CONFIGURATION_INVALID", str(exc)
        else:
            code, message = "AI_ANALYSIS_INTERNAL_ERROR", str(exc)
        if run_id:
            try:
                store.fail_run(run_id, code, message)
            except Exception as finalization_error:
                raise AnalysisError(
                    "AI_RUN_FINALIZATION_FAILED",
                    f"{code}: {message}; failed to finalize staging run {run_id}: {finalization_error}",
                ) from finalization_error
        raise AnalysisError(code, message) from exc
    finally:
        store.close()
