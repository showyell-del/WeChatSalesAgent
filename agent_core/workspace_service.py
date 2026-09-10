import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional


class WorkspaceError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


FACT_LABELS = {
    "mobile": "手机号",
    "landline": "电话",
    "wechat_id": "微信号",
    "explicit_need": "明确需求",
    "budget_cny": "预算",
    "age": "年龄",
    "grade": "年级",
    "available_time": "可到店时间",
    "obstacle": "阻碍",
    "region": "区域",
}


def _json_list(value: Optional[str]) -> List:
    if not value:
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise WorkspaceError(
            "WORKSPACE_DATA_INVALID",
            "Published analysis contains a non-list JSON field.",
        )
    return parsed


def _iso_datetime(timestamp: int) -> str:
    return (
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
        .astimezone()
        .strftime("%Y-%m-%d %H:%M")
    )


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def _default_account_id(connection: sqlite3.Connection) -> str:
    if _table_exists(connection, "app_state"):
        active = connection.execute(
            "SELECT value FROM app_state WHERE key='active_account'"
        ).fetchone()
        if active is not None:
            return str(active["value"])
    if _table_exists(connection, "accounts"):
        account = connection.execute(
            "SELECT account_id FROM accounts ORDER BY updated_at DESC,account_id LIMIT 1"
        ).fetchone()
        if account is not None:
            return str(account["account_id"])
    return ""


def load_snapshot(db_path: str, account_id: str = "") -> Dict:
    if not os.path.isfile(db_path):
        raise WorkspaceError(
            "PUBLISHED_ANALYSIS_MISSING", "No published lead analysis is available."
        )
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        if not account_id:
            account_id = _default_account_id(connection)
            if not account_id:
                raise WorkspaceError(
                    "PUBLISHED_ANALYSIS_MISSING",
                    "No active WeChat account is available.",
                )
        run = None
        if _table_exists(connection, "analysis_runs"):
            run = connection.execute(
                """SELECT ar.* FROM analysis_runs ar
                   JOIN corpus_runs cr ON cr.corpus_id=ar.corpus_id
                   JOIN generations g ON g.generation_id=cr.generation_id
                   WHERE ar.account_id=? AND ar.status='published'
                     AND cr.account_id=? AND cr.status='published'
                     AND g.account_id=? AND g.status='published'
                   ORDER BY ar.published_at DESC LIMIT 1""",
                (account_id, account_id, account_id),
            ).fetchone()
        if run is None:
            corpus = 0
            if _table_exists(connection, "corpus_runs") and _table_exists(
                connection, "corpus_conversations"
            ):
                corpus = connection.execute(
                    """SELECT count(*) FROM corpus_conversations cc
                       JOIN corpus_runs cr ON cr.corpus_id=cc.corpus_id
                       JOIN generations g ON g.generation_id=cr.generation_id
                       WHERE cr.account_id=? AND cr.status='published'
                         AND g.account_id=? AND g.status='published' AND cc.status='eligible'""",
                    (account_id, account_id),
                ).fetchone()[0]
            raise WorkspaceError(
                "PUBLISHED_ANALYSIS_MISSING",
                "The account has %d eligible conversations but no published DeepSeek analysis."
                % corpus,
            )

        rows = connection.execute(
            """SELECT lr.*, ac.prompt_tokens,ac.cache_hit_tokens,ac.cache_miss_tokens,
                      ac.completion_tokens,ac.total_tokens,ac.actual_cost_usd
               FROM lead_results lr
               LEFT JOIN ai_calls ac ON ac.run_id=lr.run_id AND ac.username=lr.username AND ac.status='succeeded'
               WHERE lr.run_id=? ORDER BY lr.intent_score DESC,lr.recent_contact_ts DESC,lr.username""",
            (run["run_id"],),
        ).fetchall()
        evidence_ids = []
        leads = []
        for row in rows:
            facts = _json_list(row["facts_json"])
            evidence = _json_list(row["evidence_ids_json"])
            evidence_ids.extend(evidence)
            fact_map = {}
            for fact in facts:
                field = str(fact.get("field", ""))
                value = str(fact.get("value", ""))
                if field and value:
                    fact_map.setdefault(FACT_LABELS.get(field, field), []).append(value)
            contact = " / ".join(
                fact_map.get("手机号", [])
                + fact_map.get("电话", [])
                + fact_map.get("微信号", [])
            )
            need = " / ".join(fact_map.get("明确需求", []))
            obstacle_values = _json_list(row["obstacles_json"])
            leads.append(
                {
                    "customer_id": row["username"],
                    "display_name": row["display_name"],
                    "intent_score": row["intent_score"],
                    "intent_band": row["intent_band"],
                    "recent_contact_ts": row["recent_contact_ts"],
                    "recent_contact": _iso_datetime(row["recent_contact_ts"]),
                    "need": need,
                    "obstacles": "；".join(obstacle_values),
                    "contact": contact,
                    "suggested_action": row["suggested_action"],
                    "draft_text": row["draft_text"] or "",
                    "facts": facts,
                    "evidence_ids": evidence,
                    "prompt_tokens": row["prompt_tokens"] or 0,
                    "cache_hit_tokens": row["cache_hit_tokens"] or 0,
                    "cache_miss_tokens": row["cache_miss_tokens"] or 0,
                    "completion_tokens": row["completion_tokens"] or 0,
                    "total_tokens": row["total_tokens"] or 0,
                    "actual_cost_usd": row["actual_cost_usd"] or "0",
                }
            )

        evidence_map = {}
        unique_ids = sorted(set(evidence_ids))
        if unique_ids:
            placeholders = ",".join("?" for _ in unique_ids)
            for item in connection.execute(
                "SELECT evidence_id,is_self,sender,timestamp,content FROM evidence WHERE evidence_id IN (%s)"
                % placeholders,
                unique_ids,
            ):
                evidence_map[item["evidence_id"]] = {
                    "evidence_id": item["evidence_id"],
                    "direction": "我方" if item["is_self"] else "客户",
                    "sender": item["sender"],
                    "timestamp": item["timestamp"],
                    "time": _iso_datetime(item["timestamp"]),
                    "content": item["content"],
                }
        for lead in leads:
            lead["evidence"] = [
                evidence_map[item]
                for item in lead.pop("evidence_ids")
                if item in evidence_map
            ]
        bands = Counter(item["intent_band"] for item in leads)
        recent_cutoff = int(run["published_at"] or run["started_at"]) - 30 * 86400
        metrics = {
            "customer_total": len(leads),
            "high_intent": bands["高意向"],
            "activation_needed": bands["待激活"],
            "recent_leads": sum(
                1 for item in leads if item["recent_contact_ts"] >= recent_cutoff
            ),
            "distribution": {
                name: bands[name] for name in ("高意向", "待激活", "长期培育", "排除")
            },
            "estimated_cost_usd": run["estimated_cost_usd"],
            "actual_cost_usd": run["actual_cost_usd"],
        }
        return {
            "schema_version": "workspace.v2",
            "account_id": account_id,
            "run": {
                "run_id": run["run_id"],
                "model": run["model"],
                "prompt_version": run["prompt_version"],
                "schema_version": run["schema_version"],
                "published_at": run["published_at"],
            },
            "metrics": metrics,
            "leads": leads,
        }
    except sqlite3.Error as exc:
        raise WorkspaceError("WORKSPACE_DATABASE_INVALID", str(exc)) from exc
    finally:
        connection.close()


def workspace_readiness(db_path: str) -> Dict:
    if not os.path.isfile(db_path):
        return {
            "account_id": "",
            "published_runs": 0,
            "eligible_conversations": 0,
            "lead_results": 0,
        }
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        account_id = _default_account_id(connection)
        if not account_id:
            return {
                "account_id": "",
                "published_runs": 0,
                "eligible_conversations": 0,
                "lead_results": 0,
            }
        published_runs = 0
        lead_results = 0
        if _table_exists(connection, "analysis_runs"):
            published_runs = connection.execute(
                """SELECT count(*) FROM analysis_runs ar
                   JOIN corpus_runs cr ON cr.corpus_id=ar.corpus_id
                   JOIN generations g ON g.generation_id=cr.generation_id
                   WHERE ar.account_id=? AND ar.status='published'
                     AND cr.account_id=? AND cr.status='published'
                     AND g.account_id=? AND g.status='published'""",
                (account_id, account_id, account_id),
            ).fetchone()[0]
            if _table_exists(connection, "lead_results"):
                lead_results = connection.execute(
                    """SELECT count(*)
                       FROM lead_results lr
                       JOIN analysis_runs ar ON ar.run_id=lr.run_id
                       JOIN corpus_runs cr ON cr.corpus_id=ar.corpus_id
                       JOIN generations g ON g.generation_id=cr.generation_id
                       WHERE ar.account_id=? AND ar.status='published'
                         AND cr.account_id=? AND cr.status='published'
                         AND g.account_id=? AND g.status='published'""",
                    (account_id, account_id, account_id),
                ).fetchone()[0]
        eligible = 0
        if _table_exists(connection, "corpus_runs") and _table_exists(
            connection, "corpus_conversations"
        ):
            eligible = connection.execute(
                """SELECT count(*)
                   FROM corpus_conversations cc
                   JOIN corpus_runs cr ON cr.corpus_id=cc.corpus_id
                   JOIN generations g ON g.generation_id=cr.generation_id
                   WHERE cr.account_id=? AND cr.status='published'
                     AND g.account_id=? AND g.status='published' AND cc.status='eligible'""",
                (account_id, account_id),
            ).fetchone()[0]
        return {
            "account_id": account_id,
            "published_runs": int(published_runs),
            "eligible_conversations": int(eligible),
            "lead_results": int(lead_results),
        }
    except sqlite3.Error as exc:
        raise WorkspaceError("WORKSPACE_DATABASE_INVALID", str(exc)) from exc
    finally:
        connection.close()
