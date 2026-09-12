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
            raise ChatlogError(
                "CHATLOG_DB_INVALID", "Chatlog database response is not a JSON object."
            )
        return data

    def sessions(self, limit: int = 5000, offset: int = 0) -> List[Dict]:
        data = self.get_json(
            "/api/v1/sessions",
            {"format": "json", "limit": str(limit), "offset": str(offset)},
        )
        sessions = data.get("sessions") if isinstance(data, dict) else None
        if not isinstance(sessions, list):
            raise ChatlogError(
                "CHATLOG_SESSIONS_INVALID",
                "Chatlog sessions response did not contain a sessions array.",
            )
        return sessions

    def all_sessions(self, page_size: int = 5000) -> List[Dict]:
        if page_size <= 0:
            raise ChatlogError(
                "CHATLOG_PAGE_SIZE_INVALID",
                "Chatlog session page size must be positive.",
            )
        previous_ids = set()
        limit = page_size
        while True:
            page = self.sessions(limit=limit)
            seen = set()
            for item in page:
                username = str(item.get("username") or item.get("user_name") or "")
                if not username:
                    raise ChatlogError(
                        "CHATLOG_SESSION_ID_MISSING",
                        "Chatlog returned a session without a username.",
                    )
                if username in seen:
                    raise ChatlogError("CHATLOG_SESSION_DUPLICATE", "Session list contains duplicate IDs.")
                seen.add(username)
            if not previous_ids.issubset(seen):
                raise ChatlogError("CHATLOG_SESSIONS_CHANGED", "Session list changed during full retrieval; refresh again.")
            if len(page) < limit:
                return page
            previous_ids = seen
            limit *= 2

    def history_page(
        self, chat: str, since: int, until: int, limit: int, offset: int, is_self: bool
    ) -> Dict:
        data = self.get_json(
            "/api/v1/history",
            {
                "chat": chat,
                "since": str(since),
                "until": str(until),
                "limit": str(limit),
                "offset": str(offset),
                "is_self": "true" if is_self else "false",
                "format": "json",
            },
        )
        if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
            raise ChatlogError(
                "CHATLOG_HISTORY_INVALID",
                "Chatlog history response did not contain a messages array.",
            )
        return data

    def history(
        self, chat: str, since: int, until: int, page_size: int = 500
    ) -> List[Dict]:
        if page_size <= 0:
            raise ChatlogError(
                "CHATLOG_PAGE_SIZE_INVALID",
                "Chatlog history page size must be positive.",
            )
        merged = []
        for is_self in (False, True):
            previous_ids = set()
            limit = page_size
            while True:
                page = self.history_page(chat, since, until, limit, 0, is_self)
                expected = int(page.get("total_count") or 0)
                messages = page["messages"]
                current_ids = set()
                for item in messages:
                    identity = json.dumps(item, ensure_ascii=False, sort_keys=True)
                    if identity in current_ids:
                        raise ChatlogError(
                            "CHATLOG_HISTORY_DUPLICATE",
                            "Chatlog history contains duplicate messages for %s." % chat,
                        )
                    current_ids.add(identity)
                if not previous_ids.issubset(current_ids):
                    raise ChatlogError(
                        "CHATLOG_HISTORY_CHANGED",
                        "Chatlog history changed during full retrieval for %s; sync again."
                        % chat,
                    )
                if len(messages) < limit:
                    if len(messages) != expected:
                        raise ChatlogError(
                            "CHATLOG_HISTORY_PAGINATION_LOSS",
                            "History response did not match Chatlog total for %s." % chat,
                        )
                    for item in messages:
                        row = dict(item)
                        row["is_self"] = is_self
                        merged.append(row)
                    break
                previous_ids = current_ids
                limit *= 2
        merged.sort(
            key=lambda item: (
                int(item.get("timestamp") or 0),
                int(item.get("local_id") or 0),
                bool(item.get("is_self")),
            )
        )
        return merged

    def get_json(self, path: str, query: Optional[Dict[str, str]] = None) -> Dict:
        raw = self.get_text(path, query)
        if raw.startswith("200 OK\n"):
            raw = raw.split("\n", 1)[1]
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ChatlogError(
                "CHATLOG_JSON_INVALID", "Chatlog response is not valid JSON: %s" % exc
            ) from exc

    def get_text(self, path: str, query: Optional[Dict[str, str]] = None) -> str:
        url = "http://%s%s" % (self.addr, path)
        if query:
            url += "?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise ChatlogError(
                "CHATLOG_SERVICE_UNAVAILABLE",
                "Chatlog service is unavailable at %s." % self.addr,
            ) from exc


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
