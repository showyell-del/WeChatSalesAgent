import hashlib
import json
import sqlite3
import time
import uuid
from typing import Dict, Iterable, List


CORPUS_SCHEMA = """
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS corpus_runs (
    corpus_id TEXT PRIMARY KEY,
    generation_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    since_ts INTEGER NOT NULL,
    until_ts INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at INTEGER NOT NULL,
    published_at INTEGER,
    failure_code TEXT,
    failure_message TEXT,
    FOREIGN KEY(generation_id) REFERENCES generations(generation_id)
);

CREATE TABLE IF NOT EXISTS corpus_conversations (
    corpus_id TEXT NOT NULL,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL,
    exclusion_code TEXT,
    inbound_count INTEGER NOT NULL,
    outbound_count INTEGER NOT NULL,
    latest_timestamp INTEGER NOT NULL,
    PRIMARY KEY(corpus_id, username),
    FOREIGN KEY(corpus_id) REFERENCES corpus_runs(corpus_id)
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    corpus_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    generation_id TEXT NOT NULL,
    username TEXT NOT NULL,
    local_id INTEGER NOT NULL,
    is_self INTEGER NOT NULL,
    sender TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    message_type TEXT NOT NULL,
    content TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    FOREIGN KEY(corpus_id) REFERENCES corpus_runs(corpus_id)
);

CREATE TABLE IF NOT EXISTS extracted_facts (
    corpus_id TEXT NOT NULL,
    username TEXT NOT NULL,
    field TEXT NOT NULL,
    value TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    extractor TEXT NOT NULL,
    PRIMARY KEY(corpus_id, username, field, value, evidence_id),
    FOREIGN KEY(corpus_id) REFERENCES corpus_runs(corpus_id),
    FOREIGN KEY(evidence_id) REFERENCES evidence(evidence_id)
);

CREATE TABLE IF NOT EXISTS corpus_evidence (
    corpus_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    PRIMARY KEY(corpus_id, evidence_id),
    FOREIGN KEY(corpus_id) REFERENCES corpus_runs(corpus_id),
    FOREIGN KEY(evidence_id) REFERENCES evidence(evidence_id)
);

CREATE INDEX IF NOT EXISTS evidence_by_conversation ON evidence(corpus_id, username, timestamp);
CREATE INDEX IF NOT EXISTS evidence_by_username ON evidence(username, timestamp);
CREATE INDEX IF NOT EXISTS facts_by_conversation ON extracted_facts(corpus_id, username, field);
"""


def evidence_id(account_id: str, generation_id: str, username: str, message: Dict) -> str:
    content = str(message.get("content", ""))
    identity = {
        "account_id": account_id,
        "generation_id": generation_id,
        "username": username,
        "local_id": int(message.get("local_id") or 0),
        "is_self": bool(message.get("is_self")),
        "sender": str(message.get("sender", "")),
        "timestamp": int(message.get("timestamp") or 0),
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }
    raw = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "ev_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CorpusStore:
    def __init__(self, connection: sqlite3.Connection):
        self.conn = connection
        self.conn.executescript(CORPUS_SCHEMA)
        self.conn.execute("INSERT OR IGNORE INTO corpus_evidence(corpus_id,evidence_id) SELECT corpus_id,evidence_id FROM evidence")
        self.conn.commit()

    def published_generation(self, account_id: str) -> Dict:
        row = self.conn.execute(
            "SELECT * FROM generations WHERE account_id=? AND status='published' ORDER BY published_at DESC LIMIT 1",
            (account_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("PUBLISHED_GENERATION_MISSING")
        return dict(row)

    def sessions(self, generation_id: str) -> List[Dict]:
        return [dict(row) for row in self.conn.execute(
            "SELECT * FROM sessions WHERE generation_id=? ORDER BY timestamp DESC, username",
            (generation_id,),
        )]

    def create_run(self, generation_id: str, account_id: str, since_ts: int, until_ts: int) -> str:
        corpus_id = "corpus_" + uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO corpus_runs(corpus_id,generation_id,account_id,since_ts,until_ts,status,started_at) VALUES(?,?,?,?,?,'staging',?)",
            (corpus_id, generation_id, account_id, since_ts, until_ts, int(time.time())),
        )
        self.conn.commit()
        return corpus_id

    def add_conversation(self, corpus_id: str, session: Dict, status: str, exclusion_code: str, inbound: int, outbound: int, latest: int) -> None:
        self.conn.execute(
            "INSERT INTO corpus_conversations VALUES(?,?,?,?,?,?,?,?)",
            (corpus_id, session["username"], session.get("chat", ""), status, exclusion_code or None, inbound, outbound, latest),
        )

    def add_evidence_and_facts(self, corpus_id: str, account_id: str, generation_id: str, username: str, message: Dict, facts: Iterable[Dict]) -> str:
        content = str(message.get("content", ""))
        item_id = evidence_id(account_id, generation_id, username, message)
        self.conn.execute(
            "INSERT OR IGNORE INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (item_id, corpus_id, account_id, generation_id, username, int(message.get("local_id") or 0), 1 if message.get("is_self") else 0, str(message.get("sender", "")), int(message.get("timestamp") or 0), str(message.get("type", "")), content, hashlib.sha256(content.encode("utf-8")).hexdigest()),
        )
        self.conn.execute("INSERT INTO corpus_evidence(corpus_id,evidence_id) VALUES(?,?)", (corpus_id, item_id))
        for fact in facts:
            self.conn.execute(
                "INSERT OR IGNORE INTO extracted_facts VALUES(?,?,?,?,?,?)",
                (corpus_id, username, fact["field"], fact["value"], item_id, fact["extractor"]),
            )
        return item_id

    def commit_conversation(self) -> None:
        self.conn.commit()

    def fail_run(self, corpus_id: str, code: str, message: str) -> None:
        self.conn.execute("UPDATE corpus_runs SET status='failed', failure_code=?, failure_message=? WHERE corpus_id=?", (code, message, corpus_id))
        self.conn.commit()

    def publish_run(self, corpus_id: str, account_id: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE corpus_runs SET status='old' WHERE account_id=? AND status='published'", (account_id,))
            self.conn.execute("UPDATE corpus_runs SET status='published', published_at=? WHERE corpus_id=?", (int(time.time()), corpus_id))

    def run_counts(self, corpus_id: str) -> Dict[str, int]:
        conversation = self.conn.execute(
            "SELECT count(*) total, sum(CASE WHEN status='eligible' THEN 1 ELSE 0 END) eligible, sum(CASE WHEN status='excluded' THEN 1 ELSE 0 END) excluded FROM corpus_conversations WHERE corpus_id=?",
            (corpus_id,),
        ).fetchone()
        evidence_count = self.conn.execute("SELECT count(*) FROM corpus_evidence WHERE corpus_id=?", (corpus_id,)).fetchone()[0]
        fact_count = self.conn.execute("SELECT count(*) FROM extracted_facts WHERE corpus_id=?", (corpus_id,)).fetchone()[0]
        return {"total": conversation[0] or 0, "eligible": conversation[1] or 0, "excluded": conversation[2] or 0, "evidence": evidence_count, "facts": fact_count}
