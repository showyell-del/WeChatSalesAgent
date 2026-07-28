import json
import sqlite3
import time
import uuid
from decimal import Decimal
from typing import Dict, List


AI_SCHEMA = """
PRAGMA foreign_keys=ON;

CREATE INDEX IF NOT EXISTS evidence_by_username ON evidence(username, timestamp);

CREATE TABLE IF NOT EXISTS ai_settings (
    setting_id INTEGER PRIMARY KEY CHECK(setting_id=1),
    base_url TEXT NOT NULL,
    model TEXT NOT NULL,
    max_tokens INTEGER NOT NULL,
    cache_hit_usd_per_million TEXT NOT NULL,
    cache_miss_usd_per_million TEXT NOT NULL,
    output_usd_per_million TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS business_profiles (
    profile_id INTEGER PRIMARY KEY CHECK(profile_id=1),
    profile_json TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id TEXT PRIMARY KEY,
    corpus_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    status TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    prompt_sha256 TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    config_snapshot_json TEXT NOT NULL,
    candidate_count INTEGER NOT NULL,
    started_at INTEGER NOT NULL,
    published_at INTEGER,
    failure_code TEXT,
    failure_message TEXT,
    estimated_cost_usd TEXT NOT NULL,
    actual_cost_usd TEXT NOT NULL,
    FOREIGN KEY(corpus_id) REFERENCES corpus_runs(corpus_id)
);

CREATE TABLE IF NOT EXISTS ai_calls (
    call_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    username TEXT NOT NULL,
    status TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    provider_response_id TEXT,
    provider_model TEXT,
    system_fingerprint TEXT,
    finish_reason TEXT,
    prompt_tokens INTEGER,
    cache_hit_tokens INTEGER,
    cache_miss_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    usage_json TEXT,
    estimated_cost_usd TEXT NOT NULL,
    actual_cost_usd TEXT,
    response_sha256 TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at INTEGER NOT NULL,
    FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id)
);

CREATE TABLE IF NOT EXISTS lead_results (
    run_id TEXT NOT NULL,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    intent_score INTEGER NOT NULL,
    intent_band TEXT NOT NULL,
    recent_contact_ts INTEGER NOT NULL,
    evidence_ids_json TEXT NOT NULL,
    obstacles_json TEXT NOT NULL,
    suggested_action TEXT NOT NULL,
    draft_text TEXT,
    draft_evidence_ids_json TEXT NOT NULL,
    facts_json TEXT NOT NULL,
    PRIMARY KEY(run_id, username),
    FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id)
);
"""

CALL_COLUMNS = (
    "call_id", "run_id", "username", "status", "request_sha256", "provider_response_id", "provider_model",
    "system_fingerprint", "finish_reason", "prompt_tokens", "cache_hit_tokens", "cache_miss_tokens",
    "completion_tokens", "total_tokens", "usage_json", "estimated_cost_usd", "actual_cost_usd", "response_sha256",
    "error_code", "error_message", "created_at",
)


class AnalysisStore:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(AI_SCHEMA)
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(ai_calls)")}
        if "usage_json" not in columns:
            self.conn.execute("ALTER TABLE ai_calls ADD COLUMN usage_json TEXT")
            self.conn.commit()

    def close(self):
        self.conn.close()

    def configure(self, settings: Dict, profile_json: str):
        now = int(time.time())
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO ai_settings VALUES(1,?,?,?,?,?,?,?)",
                (settings["base_url"], settings["model"], settings["max_tokens"], settings["cache_hit_usd_per_million"], settings["cache_miss_usd_per_million"], settings["output_usd_per_million"], now),
            )
            self.conn.execute("INSERT OR REPLACE INTO business_profiles VALUES(1,?,?)", (profile_json, now))

    def config(self) -> Dict:
        settings = self.conn.execute("SELECT * FROM ai_settings WHERE setting_id=1").fetchone()
        profile = self.conn.execute("SELECT * FROM business_profiles WHERE profile_id=1").fetchone()
        if settings is None or profile is None:
            raise RuntimeError("AI_CONFIGURATION_MISSING")
        result = dict(settings)
        result["business_profile"] = json.loads(profile["profile_json"])
        return result

    def update_business_profile(self, profile_json: str) -> None:
        now = int(time.time())
        with self.conn:
            existing = self.conn.execute("SELECT profile_id FROM business_profiles WHERE profile_id=1").fetchone()
            if existing is None:
                raise RuntimeError("AI_CONFIGURATION_MISSING")
            self.conn.execute("UPDATE business_profiles SET profile_json=?,updated_at=? WHERE profile_id=1", (profile_json, now))

    def published_corpus(self, account_id: str) -> Dict:
        row = self.conn.execute("SELECT * FROM corpus_runs WHERE account_id=? AND status='published' ORDER BY published_at DESC LIMIT 1", (account_id,)).fetchone()
        if row is None:
            raise RuntimeError("PUBLISHED_CORPUS_MISSING")
        return dict(row)

    def candidates(self, corpus_id: str, lead_keywords: List[str], minor_data_approved: bool = False) -> Dict:
        rows = self.conn.execute(
            """SELECT cc.username,cc.display_name,cc.latest_timestamp,
                      count(distinct f.evidence_id) fact_evidence_count
               FROM corpus_conversations cc
               LEFT JOIN extracted_facts f ON f.corpus_id=cc.corpus_id AND f.username=cc.username
               WHERE cc.corpus_id=? AND cc.status='eligible'
               GROUP BY cc.username,cc.display_name,cc.latest_timestamp
               ORDER BY cc.latest_timestamp DESC""",
            (corpus_id,),
        ).fetchall()
        no_fact = {row["username"] for row in rows if not row["fact_evidence_count"]}
        keyword_users = set()
        if no_fact:
            for evidence_row in self.conn.execute(
                """SELECT e.username,e.content FROM evidence e
                   JOIN corpus_evidence ce ON ce.evidence_id=e.evidence_id
                   JOIN corpus_conversations cc ON cc.corpus_id=ce.corpus_id AND cc.username=e.username
                   WHERE ce.corpus_id=? AND cc.status='eligible' AND e.is_self=0""",
                (corpus_id,),
            ):
                if evidence_row["username"] not in no_fact:
                    continue
                content = evidence_row["content"].lower()
                if any(keyword.lower() in content for keyword in lead_keywords):
                    keyword_users.add(evidence_row["username"])
        candidates = []
        privacy_excluded = 0
        for row in rows:
            item = dict(row)
            if item["fact_evidence_count"] or item["username"] in keyword_users:
                if not minor_data_approved:
                    ages = [fact[0] for fact in self.conn.execute(
                        "SELECT value FROM extracted_facts WHERE corpus_id=? AND username=? AND field='age'",
                        (corpus_id, item["username"]),
                    )]
                    if any(value.isdigit() and int(value) < 14 for value in ages):
                        privacy_excluded += 1
                        continue
                candidates.append(item)
        return {"candidates": candidates, "privacy_excluded": privacy_excluded}

    def packet(self, corpus_id: str, username: str, max_evidence: int = 18, max_chars: int = 7000) -> Dict:
        fact_rows = [dict(row) for row in self.conn.execute(
            """SELECT f.field,f.value,f.evidence_id,f.extractor,e.timestamp
               FROM extracted_facts f JOIN evidence e ON e.evidence_id=f.evidence_id
               WHERE f.corpus_id=? AND f.username=? ORDER BY e.timestamp DESC""",
            (corpus_id, username),
        )]
        latest_by_value = {}
        for row in fact_rows:
            latest_by_value.setdefault((row["field"], row["value"]), row)
        priority = {name: index for index, name in enumerate((
            "mobile", "landline", "wechat_id", "explicit_need", "budget_cny",
            "age", "grade", "available_time", "obstacle", "region",
        ))}
        selected_facts = sorted(
            latest_by_value.values(),
            key=lambda row: (priority.get(row["field"], 99), -row["timestamp"], row["value"]),
        )[:max_evidence]
        facts = [{key: row[key] for key in ("field", "value", "evidence_id", "extractor")} for row in selected_facts]
        fact_ids = {item["evidence_id"] for item in facts}
        rows = [dict(row) for row in self.conn.execute(
            """SELECT e.evidence_id,e.is_self,e.sender,e.timestamp,e.message_type,e.content
               FROM corpus_evidence ce JOIN evidence e ON e.evidence_id=ce.evidence_id
               WHERE ce.corpus_id=? AND e.username=? ORDER BY e.timestamp DESC,e.local_id DESC""",
            (corpus_id, username),
        )]
        ordered = sorted(rows, key=lambda row: (row["evidence_id"] not in fact_ids, -row["timestamp"]))
        selected = []
        chars = 0
        for item in ordered:
            content = item["content"]
            if item["evidence_id"] in fact_ids and (len(selected) >= max_evidence or chars + len(content) > max_chars):
                raise RuntimeError("AI_CONTEXT_TOO_LARGE")
            if selected and (len(selected) >= max_evidence or chars + len(content) > max_chars):
                continue
            item["content"] = content
            selected.append(item)
            chars += len(content)
        selected.sort(key=lambda row: row["timestamp"])
        if not fact_ids.issubset({item["evidence_id"] for item in selected}):
            raise RuntimeError("AI_CONTEXT_TOO_LARGE")
        return {"facts": facts, "evidence": selected}

    def create_run(self, corpus_id: str, account_id: str, metadata: Dict, candidate_count: int, estimated_cost: Decimal) -> str:
        run_id = "analysis_" + uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO analysis_runs VALUES(?,?,?,'staging',?,?,?,?,?,?,?,NULL,NULL,NULL,?,?)",
            (run_id, corpus_id, account_id, metadata["model"], metadata["prompt_version"], metadata["prompt_sha256"], metadata["schema_version"], json.dumps(metadata["config_snapshot"], ensure_ascii=False, sort_keys=True), candidate_count, int(time.time()), str(estimated_cost), "0"),
        )
        self.conn.commit()
        return run_id

    def add_call(self, values: Dict):
        columns = ",".join(CALL_COLUMNS)
        placeholders = ",".join("?" for _ in CALL_COLUMNS)
        self.conn.execute(
            "INSERT INTO ai_calls(%s) VALUES(%s)" % (columns, placeholders),
            tuple(values[key] for key in CALL_COLUMNS),
        )
        self.conn.commit()

    def add_result(self, run_id: str, username: str, display_name: str, judgment, facts: List[Dict]):
        self.conn.execute(
            "INSERT INTO lead_results VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, username, display_name, judgment.intent_score, judgment.intent_band, judgment.recent_contact_ts, json.dumps(judgment.evidence_ids, ensure_ascii=False), json.dumps(judgment.obstacles, ensure_ascii=False), judgment.suggested_action, judgment.draft_text, json.dumps(judgment.draft_evidence_ids, ensure_ascii=False), json.dumps(facts, ensure_ascii=False, sort_keys=True)),
        )
        self.conn.commit()

    def add_success(self, call_values: Dict, run_id: str, username: str, display_name: str, judgment, facts: List[Dict]):
        call_tuple = tuple(call_values[key] for key in CALL_COLUMNS)
        result_tuple = (
            run_id, username, display_name, judgment.intent_score, judgment.intent_band, judgment.recent_contact_ts,
            json.dumps(judgment.evidence_ids, ensure_ascii=False), json.dumps(judgment.obstacles, ensure_ascii=False),
            judgment.suggested_action, judgment.draft_text, json.dumps(judgment.draft_evidence_ids, ensure_ascii=False),
            json.dumps(facts, ensure_ascii=False, sort_keys=True),
        )
        with self.conn:
            self.conn.execute(
                "INSERT INTO ai_calls(%s) VALUES(%s)" % (",".join(CALL_COLUMNS), ",".join("?" for _ in CALL_COLUMNS)),
                call_tuple,
            )
            self.conn.execute("INSERT INTO lead_results VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", result_tuple)

    def fail_run(self, run_id: str, code: str, message: str):
        actual = sum(
            (Decimal(row[0]) for row in self.conn.execute("SELECT actual_cost_usd FROM ai_calls WHERE run_id=? AND actual_cost_usd IS NOT NULL", (run_id,))),
            Decimal("0"),
        )
        self.conn.execute("UPDATE analysis_runs SET status='failed',failure_code=?,failure_message=?,actual_cost_usd=? WHERE run_id=?", (code, message, str(actual), run_id))
        self.conn.commit()

    def publish_run(self, run_id: str, account_id: str):
        actual = sum(
            (Decimal(row[0]) for row in self.conn.execute("SELECT actual_cost_usd FROM ai_calls WHERE run_id=? AND actual_cost_usd IS NOT NULL", (run_id,))),
            Decimal("0"),
        )
        with self.conn:
            self.conn.execute("UPDATE analysis_runs SET status='old' WHERE account_id=? AND status='published'", (account_id,))
            self.conn.execute("UPDATE analysis_runs SET status='published',published_at=?,actual_cost_usd=? WHERE run_id=?", (int(time.time()), str(actual), run_id))
