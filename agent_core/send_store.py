import json
import sqlite3
import time
import uuid
from typing import Dict, Iterable, List, Optional

from .workspace_service import WorkspaceError, load_snapshot


SEND_SCHEMA = """
CREATE TABLE IF NOT EXISTS send_batches (
    batch_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    status TEXT NOT NULL,
    message_text TEXT NOT NULL,
    attachments_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    started_at INTEGER,
    ended_at INTEGER,
    total INTEGER NOT NULL,
    succeeded INTEGER NOT NULL,
    failed INTEGER NOT NULL,
    blocked_code TEXT,
    blocked_message TEXT
);

CREATE TABLE IF NOT EXISTS send_recipients (
    batch_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    final_text TEXT NOT NULL,
    status TEXT NOT NULL,
    queued_at INTEGER NOT NULL,
    sent_at INTEGER,
    result_code TEXT,
    result_message TEXT,
    PRIMARY KEY(batch_id, customer_id),
    FOREIGN KEY(batch_id) REFERENCES send_batches(batch_id)
);

CREATE INDEX IF NOT EXISTS send_recipients_by_customer
ON send_recipients(customer_id, queued_at DESC);
"""

ACTIONABLE_BANDS = {"高意向", "待激活"}
STATUS_LABELS = {
    "queued": "已排队",
    "blocked": "发送阻断",
    "sending": "发送中",
    "succeeded": "发送成功",
    "failed": "发送失败",
    "cancelled": "已取消",
}


class SendError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class SendStore:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SEND_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def _published_run_id(self, account_id: str) -> str:
        row = self.conn.execute(
            "SELECT run_id FROM analysis_runs WHERE account_id=? AND status='published' ORDER BY published_at DESC LIMIT 1",
            (account_id,),
        ).fetchone()
        if row is None:
            raise SendError("PUBLISHED_ANALYSIS_MISSING", "No published lead analysis is available for sending.")
        return str(row["run_id"])

    def create_batch(
        self,
        account_id: str,
        message_text: str,
        customer_ids: Optional[Iterable[str]] = None,
        bands: Optional[Iterable[str]] = None,
        attachments: Optional[Iterable[str]] = None,
    ) -> Dict:
        text = message_text.strip()
        if not text:
            raise SendError("SEND_TEXT_EMPTY", "Batch send text cannot be empty.")
        attachment_list = [item for item in (attachments or []) if str(item).strip()]
        run_id = self._published_run_id(account_id)
        snapshot = load_snapshot(self.conn.execute("PRAGMA database_list").fetchone()["file"], account_id)
        wanted_ids = {item.strip() for item in (customer_ids or []) if item.strip()}
        wanted_bands = set(bands or ACTIONABLE_BANDS)
        selected = []
        for lead in snapshot["leads"]:
            if wanted_ids and lead["customer_id"] not in wanted_ids:
                continue
            if not wanted_ids and lead["intent_band"] not in wanted_bands:
                continue
            selected.append(lead)
        if not selected:
            raise SendError("SEND_RECIPIENTS_EMPTY", "No actionable lead recipients matched the send batch.")
        now = int(time.time())
        batch_id = "send_" + uuid.uuid4().hex
        with self.conn:
            self.conn.execute(
                "INSERT INTO send_batches VALUES(?,?,?,?,?,?,?,NULL,NULL,?,0,0,NULL,NULL)",
                (batch_id, account_id, run_id, "queued", text, json.dumps(attachment_list, ensure_ascii=False), now, len(selected)),
            )
            self.conn.executemany(
                "INSERT INTO send_recipients VALUES(?,?,?,?,?, ?,NULL,NULL,NULL)",
                [
                    (
                        batch_id,
                        lead["customer_id"],
                        lead["display_name"],
                        text.replace("{客户}", lead["display_name"] or "客户").replace("{称呼}", lead["display_name"] or "客户"),
                        "queued",
                        now,
                    )
                    for lead in selected
                ],
            )
        return self.batch(batch_id)

    def batch(self, batch_id: str) -> Dict:
        batch = self.conn.execute("SELECT * FROM send_batches WHERE batch_id=?", (batch_id,)).fetchone()
        if batch is None:
            raise SendError("SEND_BATCH_NOT_FOUND", "Send batch was not found.")
        recipients = [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM send_recipients WHERE batch_id=? ORDER BY queued_at, display_name, customer_id",
                (batch_id,),
            )
        ]
        result = dict(batch)
        result["attachments"] = json.loads(result.pop("attachments_json"))
        result["recipients"] = recipients
        result["status_label"] = STATUS_LABELS.get(result["status"], result["status"])
        return result

    def list_batches(self, account_id: str = "") -> List[Dict]:
        if account_id:
            rows = self.conn.execute("SELECT * FROM send_batches WHERE account_id=? ORDER BY created_at DESC", (account_id,))
        else:
            rows = self.conn.execute("SELECT * FROM send_batches ORDER BY created_at DESC")
        result = []
        for row in rows:
            item = dict(row)
            item["attachments"] = json.loads(item.pop("attachments_json"))
            item["status_label"] = STATUS_LABELS.get(item["status"], item["status"])
            result.append(item)
        return result

    def block_batch(self, batch_id: str, code: str, message: str) -> Dict:
        now = int(time.time())
        with self.conn:
            updated = self.conn.execute(
                """UPDATE send_batches
                   SET status='blocked', started_at=COALESCE(started_at,?), ended_at=?, failed=total,
                       blocked_code=?, blocked_message=?
                   WHERE batch_id=?""",
                (now, now, code, message, batch_id),
            )
            if updated.rowcount != 1:
                raise SendError("SEND_BATCH_NOT_FOUND", "Send batch was not found.")
            self.conn.execute(
                """UPDATE send_recipients
                   SET status='blocked', result_code=?, result_message=?
                   WHERE batch_id=? AND status='queued'""",
                (code, message, batch_id),
            )
        return self.batch(batch_id)


def latest_send_statuses(db_path: str, account_id: str, run_id: str) -> Dict[str, str]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(SEND_SCHEMA)
        rows = connection.execute(
            """SELECT sr.customer_id,sr.status
               FROM send_recipients sr
               JOIN send_batches sb ON sb.batch_id=sr.batch_id
               JOIN (
                   SELECT sr2.customer_id,max(sr2.queued_at) queued_at
                   FROM send_recipients sr2
                   JOIN send_batches sb2 ON sb2.batch_id=sr2.batch_id
                   WHERE sb2.account_id=? AND sb2.run_id=?
                   GROUP BY sr2.customer_id
               ) latest ON latest.customer_id=sr.customer_id AND latest.queued_at=sr.queued_at
               WHERE sb.account_id=? AND sb.run_id=?""",
            (account_id, run_id, account_id, run_id),
        )
        return {row["customer_id"]: STATUS_LABELS.get(row["status"], row["status"]) for row in rows}
    except sqlite3.Error as exc:
        raise WorkspaceError("WORKSPACE_DATABASE_INVALID", str(exc)) from exc
    finally:
        connection.close()
