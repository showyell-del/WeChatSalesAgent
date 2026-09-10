import os
import sqlite3
import time
import uuid
from typing import Dict, Iterable, List


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    data_root TEXT NOT NULL,
    status TEXT NOT NULL,
    last_error_code TEXT,
    last_error_message TEXT,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS generations (
    generation_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at INTEGER NOT NULL,
    published_at INTEGER,
    error_code TEXT,
    error_message TEXT,
    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
);

CREATE TABLE IF NOT EXISTS db_files (
    generation_id TEXT NOT NULL,
    group_name TEXT NOT NULL,
    path TEXT NOT NULL,
    exists_on_disk INTEGER NOT NULL,
    PRIMARY KEY(generation_id, group_name, path),
    FOREIGN KEY(generation_id) REFERENCES generations(generation_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    generation_id TEXT NOT NULL,
    username TEXT NOT NULL,
    chat TEXT NOT NULL,
    chat_type TEXT NOT NULL,
    is_group INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    summary TEXT NOT NULL,
    PRIMARY KEY(generation_id, username),
    FOREIGN KEY(generation_id) REFERENCES generations(generation_id)
);
"""


class SyncStore:
    def __init__(self, path: str):
        self.path = path
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._ensure_column(
            "accounts", "verified_db_count", "INTEGER NOT NULL DEFAULT 0"
        )

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(%s)" % table)}
        if column not in columns:
            self.conn.execute(
                "ALTER TABLE %s ADD COLUMN %s %s" % (table, column, definition)
            )
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def upsert_account(
        self,
        account_id: str,
        data_root: str,
        status: str,
        error_code: str = "",
        error_message: str = "",
    ) -> None:
        now = int(time.time())
        self.conn.execute(
            """
            INSERT INTO accounts(account_id, data_root, status, last_error_code, last_error_message, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                data_root=excluded.data_root,
                status=excluded.status,
                last_error_code=excluded.last_error_code,
                last_error_message=excluded.last_error_message,
                updated_at=excluded.updated_at
            """,
            (
                account_id,
                data_root,
                status,
                error_code or None,
                error_message or None,
                now,
            ),
        )
        self.conn.commit()

    def mark_key_verified(self, account_id: str, verified_db_count: int) -> None:
        self.conn.execute(
            "UPDATE accounts SET status='key_verified', verified_db_count=?, updated_at=?, last_error_code=NULL, last_error_message=NULL WHERE account_id=?",
            (verified_db_count, int(time.time()), account_id),
        )
        self.conn.commit()

    def set_active_account(self, account_id: str) -> None:
        existing = self.conn.execute(
            "SELECT 1 FROM accounts WHERE account_id=?", (account_id,)
        ).fetchone()
        if existing is None:
            raise RuntimeError("ACTIVE_ACCOUNT_NOT_FOUND")
        self.conn.execute(
            "INSERT OR REPLACE INTO app_state(key,value,updated_at) VALUES('active_account',?,?)",
            (account_id, int(time.time())),
        )
        self.conn.commit()

    def create_generation(self, account_id: str) -> str:
        generation_id = "%s-%s" % (account_id, uuid.uuid4().hex)
        self.conn.execute(
            "INSERT INTO generations(generation_id, account_id, status, started_at) VALUES (?, ?, ?, ?)",
            (generation_id, account_id, "staging", int(time.time())),
        )
        self.conn.commit()
        return generation_id

    def fail_generation(self, generation_id: str, code: str, message: str) -> None:
        self.conn.execute(
            "UPDATE generations SET status='failed', error_code=?, error_message=? WHERE generation_id=?",
            (code, message, generation_id),
        )
        self.conn.commit()

    def publish_generation(self, generation_id: str, account_id: str) -> None:
        now = int(time.time())
        with self.conn:
            self.conn.execute(
                "UPDATE generations SET status='old' WHERE account_id=? AND status='published'",
                (account_id,),
            )
            self.conn.execute(
                "UPDATE generations SET status='published', published_at=? WHERE generation_id=?",
                (now, generation_id),
            )
            self.conn.execute(
                "UPDATE accounts SET status='verified', updated_at=?, last_error_code=NULL, last_error_message=NULL WHERE account_id=?",
                (now, account_id),
            )
            tables = {
                row[0]
                for row in self.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "corpus_runs" in tables:
                self.conn.execute(
                    "UPDATE corpus_runs SET status='old' WHERE account_id=? AND status='published' AND generation_id<>?",
                    (account_id, generation_id),
                )
            if "analysis_runs" in tables:
                self.conn.execute(
                    "UPDATE analysis_runs SET status='superseded' WHERE account_id=? AND status='published'",
                    (account_id,),
                )

    def insert_db_files(self, generation_id: str, db_map: Dict[str, List[str]]) -> None:
        rows = []
        for group_name, paths in sorted(db_map.items()):
            for path in paths:
                rows.append(
                    (generation_id, group_name, path, 1 if os.path.exists(path) else 0)
                )
        self.conn.executemany(
            "INSERT OR REPLACE INTO db_files(generation_id, group_name, path, exists_on_disk) VALUES (?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()

    def insert_sessions(self, generation_id: str, sessions: Iterable[Dict]) -> int:
        rows = []
        for item in sessions:
            rows.append(
                (
                    generation_id,
                    str(item.get("username", "")),
                    str(item.get("chat", "")),
                    str(item.get("chat_type", "")),
                    1 if item.get("is_group") else 0,
                    int(item.get("timestamp") or 0),
                    str(item.get("summary", "")),
                )
            )
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO sessions(generation_id, username, chat, chat_type, is_group, timestamp, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()
        return len(rows)

    def status(self) -> Dict:
        accounts = [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM accounts ORDER BY updated_at DESC"
            )
        ]
        generations = [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM generations ORDER BY started_at DESC LIMIT 20"
            )
        ]
        return {"accounts": accounts, "generations": generations}
