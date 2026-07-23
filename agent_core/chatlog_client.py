import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Iterable, List, Optional


class ChatlogError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ChatlogClient:
    def __init__(self, addr: str = "127.0.0.1:5030", timeout: int = 30):
        self.addr = addr
        self.timeout = timeout

    def health(self) -> Dict:
        return self.get_json("/health")

    def databases(self) -> Dict[str, List[str]]:
        data = self.get_json("/api/v1/db")
        if not isinstance(data, dict):
            raise ChatlogError("CHATLOG_DB_INVALID", "Chatlog database response is not a JSON object.")
        return data

    def sessions(self, limit: int = 5000, offset: int = 0) -> List[Dict]:
        data = self.get_json("/api/v1/sessions", {"format": "json", "limit": str(limit), "offset": str(offset)})
        sessions = data.get("sessions") if isinstance(data, dict) else None
        if not isinstance(sessions, list):
            raise ChatlogError("CHATLOG_SESSIONS_INVALID", "Chatlog sessions response did not contain a sessions array.")
        return sessions

    def get_json(self, path: str, query: Optional[Dict[str, str]] = None) -> Dict:
        raw = self.get_text(path, query)
        if raw.startswith("200 OK\n"):
            raw = raw.split("\n", 1)[1]
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ChatlogError("CHATLOG_JSON_INVALID", "Chatlog response is not valid JSON: %s" % exc) from exc

    def get_text(self, path: str, query: Optional[Dict[str, str]] = None) -> str:
        url = "http://%s%s" % (self.addr, path)
        if query:
            url += "?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise ChatlogError("CHATLOG_SERVICE_UNAVAILABLE", "Chatlog service is unavailable at %s." % self.addr) from exc


def iter_db_paths(db_map: Dict[str, Iterable[str]]) -> Iterable[str]:
    for paths in db_map.values():
        if isinstance(paths, list):
            for path in paths:
                if isinstance(path, str):
                    yield path


def derive_account_ids(db_map: Dict[str, Iterable[str]]) -> List[str]:
    account_ids = set()
    marker = "/xwechat_files/"
    suffix = "/db_storage/"
    for path in iter_db_paths(db_map):
        if marker not in path or suffix not in path:
            continue
        after_marker = path.split(marker, 1)[1]
        account_id = after_marker.split(suffix, 1)[0]
        if account_id:
            account_ids.add(account_id)
    return sorted(account_ids)

