import argparse
import json
import os
import sys
from decimal import Decimal

from pydantic import ValidationError

from .ai_models import BusinessProfile
from .analysis_engine import AnalysisError, estimate_run, run_analysis
from .analysis_store import AnalysisStore
from .chatlog_client import ChatlogError
from .events import emit, event
from .keychain import KeychainStore


DEEPSEEK_KEYCHAIN_SERVICE = "com.wechat-sales-agent.deepseek-api-key"
MAX_OUTPUT_TOKENS = 8192


def validate_limit(value: int) -> None:
    if value < 0:
        raise AnalysisError("AI_LIMIT_INVALID", "Analysis limit cannot be negative.")


def command_set_key(args):
    try:
        key = sys.stdin.read().strip()
        if not key:
            raise AnalysisError(
                "DEEPSEEK_API_KEY_EMPTY", "DeepSeek API Key cannot be empty."
            )
        KeychainStore(DEEPSEEK_KEYCHAIN_SERVICE).put_and_verify("default", key)
        emit(
            event(
                "ai_key",
                "passed",
                "DEEPSEEK_API_KEY_SAVED",
                "DeepSeek API Key saved to macOS Keychain.",
            )
        )
        return 0
    except (RuntimeError, AnalysisError) as exc:
        code = (
            exc.code
            if isinstance(exc, AnalysisError)
            else "DEEPSEEK_API_KEY_SAVE_FAILED"
        )
        message = exc.message if isinstance(exc, AnalysisError) else str(exc)
        emit(event("ai_key", "failed", code, message))
        return 1


def command_approve_transfer(args):
    try:
        store = AnalysisStore(args.db)
        try:
            config = store.config()
            profile = BusinessProfile.model_validate(config["business_profile"])
            updated = profile.model_copy(
                update={"external_api_data_transfer_approved": True}
            )
            store.update_business_profile(updated.model_dump_json())
        finally:
            store.close()
        emit(
            event(
                "ai_config",
                "passed",
                "AI_EXTERNAL_TRANSFER_APPROVED",
                "External DeepSeek personal-data transfer approved in business configuration.",
                {
                    "minor_data_approved": str(updated.minor_data_approved).lower(),
                },
            )
        )
        return 0
    except (RuntimeError, ValidationError) as exc:
        emit(event("ai_config", "failed", "AI_TRANSFER_APPROVAL_FAILED", str(exc)))
        return 1


def command_configure(args):
    try:
        with open(args.business_file, "r", encoding="utf-8") as handle:
            business = BusinessProfile.model_validate(json.load(handle))
        if not args.base_url.startswith("https://"):
            raise ValueError("DeepSeek Base URL must use HTTPS.")
        if not args.model.strip() or not 1 <= args.max_tokens <= MAX_OUTPUT_TOKENS:
            raise ValueError("DeepSeek model and max_tokens must be valid.")
        prices = (
            Decimal(args.cache_hit_price),
            Decimal(args.cache_miss_price),
            Decimal(args.output_price),
        )
        if any(not price.is_finite() or price < 0 for price in prices):
            raise ValueError("DeepSeek token prices must be finite and non-negative.")
        settings = {
            "base_url": args.base_url.rstrip("/"),
            "model": args.model.strip(),
            "max_tokens": args.max_tokens,
            "cache_hit_usd_per_million": str(prices[0]),
            "cache_miss_usd_per_million": str(prices[1]),
            "output_usd_per_million": str(prices[2]),
        }
        key = os.environ.get(args.api_key_env, "").strip()
        if key:
            KeychainStore(DEEPSEEK_KEYCHAIN_SERVICE).put_and_verify("default", key)
        store = AnalysisStore(args.db)
        try:
            analysis_invalidated = store.configure(settings, business.model_dump_json())
        finally:
            store.close()
        emit(
            event(
                "ai_config",
                "passed",
                "AI_CONFIGURATION_SAVED",
                "DeepSeek and business configuration saved.",
                {
                    "base_url": settings["base_url"],
                    "model": settings["model"],
                    "api_key_updated": str(bool(key)).lower(),
                    "analysis_invalidated": str(analysis_invalidated).lower(),
                },
            )
        )
        return 0
    except (OSError, ValueError, ValidationError, RuntimeError) as exc:
        emit(event("ai_config", "failed", "AI_CONFIGURATION_INVALID", str(exc)))
        return 1


def command_estimate(args):
    store = None
    try:
        validate_limit(args.limit)
        store = AnalysisStore(args.db)
        result = estimate_run(store, args.account_id, args.limit)
        emit(
            event(
                "ai_estimate",
                "passed",
                "AI_COST_ESTIMATED",
                "Candidate count and conservative token cost estimated.",
                {
                    "candidates": str(len(result["candidates"])),
                    "estimated_input_tokens": str(result["estimated_input_tokens"]),
                    "estimated_output_tokens": str(result["estimated_output_tokens"]),
                    "estimated_cost_usd": str(result["estimated_cost_usd"]),
                    "privacy_excluded": str(result["privacy_excluded"]),
                    "method": "utf8_bytes_div_3_plus_configured_max_output",
                },
            )
        )
        return 0
    except Exception as exc:
        emit(event("ai_estimate", "failed", "AI_ESTIMATE_FAILED", str(exc)))
        return 1
    finally:
        if store is not None:
            store.close()


def command_run(args):
    try:
        validate_limit(args.limit)
        if args.timeout <= 0:
            raise AnalysisError(
                "AI_TIMEOUT_INVALID", "Analysis timeout must be positive."
            )
        try:
            api_key = KeychainStore(DEEPSEEK_KEYCHAIN_SERVICE).get("default")
        except ChatlogError as exc:
            raise AnalysisError(
                "DEEPSEEK_API_KEY_MISSING",
                "DeepSeek API Key is missing from macOS Keychain.",
            ) from exc
        if not api_key:
            raise AnalysisError(
                "DEEPSEEK_API_KEY_MISSING",
                "DeepSeek API Key is missing from macOS Keychain.",
            )
        result = run_analysis(
            args.db, args.account_id, api_key, args.limit, args.timeout
        )
        emit(
            event(
                "ai_analysis",
                "passed",
                "AI_ANALYSIS_PUBLISHED",
                "Strict evidence-backed lead analysis published.",
                result,
            )
        )
        return 0
    except (RuntimeError, AnalysisError) as exc:
        code = exc.code if isinstance(exc, AnalysisError) else "AI_ANALYSIS_FAILED"
        message = exc.message if isinstance(exc, AnalysisError) else str(exc)
        emit(event("ai_analysis", "failed", code, message))
        return 1


def command_status(args):
    try:
        store = AnalysisStore(args.db)
        try:
            config = store.config()
            rows = [
                dict(row)
                for row in store.conn.execute(
                    "SELECT run_id,status,model,candidate_count,estimated_cost_usd,actual_cost_usd,published_at,failure_code FROM analysis_runs ORDER BY started_at DESC LIMIT 10"
                )
            ]
        finally:
            store.close()
        emit(
            event(
                "ai_status",
                "passed",
                "AI_STATUS_READ",
                "DeepSeek configuration and analysis state loaded.",
                {
                    "model": config["model"],
                    "configured": "true",
                    "runs": str(len(rows)),
                    "published_runs": str(
                        sum(1 for row in rows if row["status"] == "published")
                    ),
                },
            )
        )
        return 0
    except Exception as exc:
        emit(event("ai_status", "failed", "AI_STATUS_FAILED", str(exc)))
        return 1


def command_profile(args):
    try:
        store = AnalysisStore(args.db)
        try:
            profile = BusinessProfile.model_validate(store.config()["business_profile"])
        finally:
            store.close()
        emit(
            event(
                "ai_profile",
                "passed",
                "AI_BUSINESS_PROFILE_READ",
                "Business profile loaded.",
            )
        )
        print(profile.model_dump_json())
        return 0
    except Exception as exc:
        emit(event("ai_profile", "failed", "AI_BUSINESS_PROFILE_READ_FAILED", str(exc)))
        return 1


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="runtime/agent_state.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("set-key").set_defaults(func=command_set_key)
    sub.add_parser("approve-transfer").set_defaults(func=command_approve_transfer)
    configure = sub.add_parser("configure")
    configure.add_argument("--business-file", required=True)
    configure.add_argument("--base-url", default="https://api.deepseek.com")
    configure.add_argument("--model", default="deepseek-v4-flash")
    configure.add_argument("--max-tokens", type=int, default=1400)
    configure.add_argument("--cache-hit-price", default="0.0028")
    configure.add_argument("--cache-miss-price", default="0.14")
    configure.add_argument("--output-price", default="0.28")
    configure.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    configure.set_defaults(func=command_configure)
    estimate = sub.add_parser("estimate")
    estimate.add_argument("--account-id", required=True)
    estimate.add_argument("--limit", type=int, default=0)
    estimate.set_defaults(func=command_estimate)
    run = sub.add_parser("run")
    run.add_argument("--account-id", required=True)
    run.add_argument("--limit", type=int, default=0)
    run.add_argument("--timeout", type=int, default=120)
    run.set_defaults(func=command_run)
    sub.add_parser("status").set_defaults(func=command_status)
    sub.add_parser("profile").set_defaults(func=command_profile)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
