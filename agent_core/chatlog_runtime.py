import json
import os
import re
import sqlite3
import subprocess
from typing import Dict, Iterable, List

from .chatlog_client import ChatlogError


HEX_KEY = re.compile(r"^[0-9a-fA-F]{64}$")


class ChatlogRuntime:
    def __init__(self, binary: str):
        self.binary = os.path.abspath(binary)

    def action(self, name: str, account_id: str = "") -> Dict:
        command = [self.binary, "action", name]
        if account_id:
            command.extend(["--history", account_id])
        try:
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
        except OSError as exc:
            raise ChatlogError("CHATLOG_BINARY_UNAVAILABLE", "Chatlog binary could not be executed.") from exc

        records = []
        for line in completed.stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        successes = [item for item in records if item.get("type") == "success" and item.get("action") == name]
        if completed.returncode != 0 or not successes:
            message = "Chatlog action %s failed." % name
            failures = [item for item in records if item.get("type") in ("error", "failed")]
            if failures and failures[-1].get("message"):
                message = str(failures[-1]["message"])
            raise ChatlogError("CHATLOG_ACTION_FAILED", message)
        return successes[-1]

    def status(self, account_id: str = "") -> Dict:
        return self.action("status", account_id).get("data") or {}

    def decompress(self, account_id: str) -> Dict:
        return self.action("decompress-data", account_id).get("data") or {}

    def obtain_key(self, account_id: str) -> Dict:
        return self.action("restart-and-get-key", account_id).get("data") or {}

    def list_accounts(self) -> List[Dict]:
        data = self.action("list-accounts").get("data") or []
        if not isinstance(data, list):
            raise ChatlogError("CHATLOG_ACCOUNTS_INVALID", "Chatlog account list is invalid.")
        return data

    def switch_account(self, account_id: str) -> Dict:
        return self.action("switch-account", account_id).get("data") or {}


def primary_db_paths(db_map: Dict[str, Iterable[str]]) -> List[str]:
    paths = []
    for group in ("session", "contact", "message"):
        for path in db_map.get(group, []):
            if isinstance(path, str) and not path.endswith("_fts.db"):
                paths.append(path)
    return sorted(set(paths))


def verify_runtime_account(status: Dict, account_id: str, db_map: Dict[str, Iterable[str]]) -> Dict:
    if status.get("account") != account_id:
        raise ChatlogError("CHATLOG_ACCOUNT_MISMATCH", "Chatlog runtime account does not match the selected account.")
    if not HEX_KEY.fullmatch(str(status.get("data_key", ""))):
        raise ChatlogError("DATABASE_KEY_MISSING", "Selected account does not have a valid database key.")

    work_dir = os.path.abspath(str(status.get("work_dir", "")))
    if not work_dir or os.path.basename(work_dir) != account_id:
        raise ChatlogError("DECRYPTED_WORKDIR_MISMATCH", "Decrypted work directory does not belong to the selected account.")

    verified = []
    for encrypted_path in primary_db_paths(db_map):
        marker = "/db_storage/"
        if marker not in encrypted_path:
            raise ChatlogError("DATABASE_PATH_INVALID", "Chatlog returned a database path outside db_storage.")
        relative = encrypted_path.split(marker, 1)[1]
        decrypted_path = os.path.join(work_dir, "db_storage", relative)
        if not os.path.isfile(decrypted_path):
            raise ChatlogError("DECRYPTED_DATABASE_MISSING", "Decrypted database is missing: %s" % relative)
        try:
            uri = "file:%s?mode=ro&immutable=1" % decrypted_path
            connection = sqlite3.connect(uri, uri=True)
            connection.execute("PRAGMA schema_version").fetchone()
            connection.close()
        except sqlite3.Error as exc:
            raise ChatlogError("DECRYPTED_DATABASE_INVALID", "Decrypted database is unreadable: %s" % relative) from exc
        verified.append(relative)

    if not verified:
        raise ChatlogError("PRIMARY_DATABASES_EMPTY", "No primary session, contact, or message databases were found.")
    return {"work_dir": work_dir, "verified_databases": verified}
