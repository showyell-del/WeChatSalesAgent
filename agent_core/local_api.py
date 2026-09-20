import argparse
import base64
import binascii
import hashlib
import hmac
import json
import os
import queue
import secrets
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Deque, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

from .chatlog_client import ChatlogClient, ChatlogError, derive_account_ids
from .customer_agent import CustomerAgentError, ask_customer_agent
from .dashboard_data import load_dashboard
from .keychain import KeychainStore
from .message_search import list_sessions, search_messages


LOCAL_API_KEYCHAIN_SERVICE = "com.wechat-sales-agent.local-api"
LOCAL_API_KEYCHAIN_ACCOUNT = "bearer-token"
DEFAULT_DB = os.path.expanduser(
    "~/Library/Application Support/WeChatSalesAgent/agent_state.sqlite3"
)
MAX_REQUEST_BYTES = 1024 * 1024
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
RATE_LIMIT_REQUESTS = 120
RATE_LIMIT_WINDOW_SECONDS = 60


class APIProblem(RuntimeError):
    def __init__(self, status: int, code: str, title: str, detail: str):
        super().__init__(detail)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail


def _problem_type(code: str) -> str:
    return "https://wechat-sales-agent.local/problems/%s" % code.lower().replace("_", "-")


def _read_active_account(db_path: str) -> str:
    if not os.path.isfile(db_path):
        raise APIProblem(
            503,
            "STATE_DB_UNAVAILABLE",
            "State database unavailable",
            "无法读取应用状态数据库。",
        )
    try:
        connection = sqlite3.connect(db_path)
        try:
            row = connection.execute(
                "SELECT value FROM app_state WHERE key='active_account'"
            ).fetchone()
        finally:
            connection.close()
    except (OSError, sqlite3.Error) as exc:
        raise APIProblem(
            503,
            "STATE_DB_UNAVAILABLE",
            "State database unavailable",
            "无法读取应用状态数据库。",
        ) from exc
    account_id = str(row[0]).strip() if row and row[0] else ""
    if not account_id:
        raise APIProblem(
            409,
            "ACTIVE_ACCOUNT_MISSING",
            "Active account missing",
            "请先在应用中连接并同步微信账号。",
        )
    return account_id


def validate_account_binding(db_path: str, chatlog_addr: str) -> str:
    active_account = _read_active_account(db_path)
    try:
        chatlog_accounts = derive_account_ids(ChatlogClient(chatlog_addr).databases())
    except ChatlogError as exc:
        raise APIProblem(
            503,
            exc.code,
            "Chatlog unavailable",
            exc.message,
        ) from exc
    if chatlog_accounts != [active_account]:
        raise APIProblem(
            409,
            "ACCOUNT_MISMATCH",
            "Account mismatch",
            "Chatlog 当前数据库账号必须与应用 active_account 完全一致。",
        )
    return active_account


def _encode_cursor(offset: int) -> str:
    raw = json.dumps({"offset": offset}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> int:
    if not value:
        return 0
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        offset = decoded["offset"]
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError
        return offset
    except (binascii.Error, KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise APIProblem(400, "CURSOR_INVALID", "Invalid cursor", "分页游标无效。") from exc


def _integer_query(query: Dict[str, list], name: str, default: int, minimum: int, maximum: int) -> int:
    raw = query.get(name, [str(default)])[0]
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise APIProblem(400, "QUERY_INVALID", "Invalid query", "%s 必须是整数。" % name) from exc
    if value < minimum or value > maximum:
        raise APIProblem(
            400,
            "QUERY_INVALID",
            "Invalid query",
            "%s 必须在 %s 到 %s 之间。" % (name, minimum, maximum),
        )
    return value


class SlidingWindowRateLimiter:
    def __init__(self, limit: int = RATE_LIMIT_REQUESTS, window: int = RATE_LIMIT_WINDOW_SECONDS):
        self.limit = limit
        self.window = window
        self._requests: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, identity: str) -> Tuple[bool, int, int]:
        now = time.monotonic()
        with self._lock:
            timestamps = self._requests[identity]
            while timestamps and timestamps[0] <= now - self.window:
                timestamps.popleft()
            if len(timestamps) >= self.limit:
                retry_after = max(1, int(self.window - (now - timestamps[0])) + 1)
                return False, 0, retry_after
            timestamps.append(now)
            return True, self.limit - len(timestamps), 0


class OperationQueue:
    def __init__(self, db_path: str, chatlog_addr: str):
        self.db_path = db_path
        self.chatlog_addr = chatlog_addr
        self.operations: Dict[str, Dict] = {}
        self.idempotency: Dict[str, Tuple[str, str]] = {}
        self._queue = queue.Queue()
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._run, name="local-api-analysis", daemon=True)
        self._worker.start()

    def submit(self, idempotency_key: str, payload: Dict, account_id: str) -> Tuple[Dict, bool]:
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        with self._lock:
            existing = self.idempotency.get(idempotency_key)
            if existing:
                existing_fingerprint, operation_id = existing
                if not hmac.compare_digest(existing_fingerprint, fingerprint):
                    raise APIProblem(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "Idempotency conflict",
                        "同一个 Idempotency-Key 不能用于不同的请求内容。",
                    )
                return dict(self.operations[operation_id]), False
            operation_id = "op_" + uuid.uuid4().hex
            operation = {
                "id": operation_id,
                "status": "queued",
                "account_id": account_id,
                "created_at": int(time.time()),
                "updated_at": int(time.time()),
            }
            self.operations[operation_id] = operation
            self.idempotency[idempotency_key] = (fingerprint, operation_id)
            self._queue.put((operation_id, payload))
            return dict(operation), True

    def get(self, operation_id: str) -> Optional[Dict]:
        with self._lock:
            operation = self.operations.get(operation_id)
            return dict(operation) if operation else None

    def _update(self, operation_id: str, **values) -> None:
        with self._lock:
            operation = self.operations[operation_id]
            operation.update(values)
            operation["updated_at"] = int(time.time())

    def _run(self) -> None:
        while True:
            operation_id, payload = self._queue.get()
            try:
                account_id = validate_account_binding(self.db_path, self.chatlog_addr)
                operation = self.get(operation_id)
                if operation is None or operation["account_id"] != account_id:
                    raise APIProblem(
                        409,
                        "ACCOUNT_MISMATCH",
                        "Account mismatch",
                        "分析操作所属账号已不是当前微信账号。",
                    )
                self._update(operation_id, status="running", started_at=int(time.time()))
                result = ask_customer_agent(
                    db=self.db_path,
                    question=payload["question"],
                    timeout=payload.get("timeout", 120),
                    session_id=payload.get("session_id", ""),
                    forced_task_type=payload.get("task_type", ""),
                )
                self._update(
                    operation_id,
                    status="succeeded",
                    completed_at=int(time.time()),
                    result=result,
                )
            except APIProblem as exc:
                self._update(
                    operation_id,
                    status="failed",
                    completed_at=int(time.time()),
                    error={"code": exc.code, "detail": exc.detail},
                )
            except (CustomerAgentError, ChatlogError) as exc:
                self._update(
                    operation_id,
                    status="failed",
                    completed_at=int(time.time()),
                    error={"code": exc.__class__.__name__, "detail": str(exc)},
                )
            except Exception:
                self._update(
                    operation_id,
                    status="failed",
                    completed_at=int(time.time()),
                    error={"code": "ANALYSIS_FAILED", "detail": "分析任务执行失败。"},
                )
            finally:
                self._queue.task_done()


class LocalAPIServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, token: str, db_path: str, chatlog_addr: str):
        host, _ = address
        if host != "127.0.0.1":
            raise ValueError("Local API may only bind to 127.0.0.1")
        super().__init__(address, LocalAPIHandler)
        self.token = token
        self.db_path = db_path
        self.chatlog_addr = chatlog_addr
        self.rate_limiter = SlidingWindowRateLimiter()
        self.operation_queue = OperationQueue(db_path, chatlog_addr)


class LocalAPIHandler(BaseHTTPRequestHandler):
    server_version = "WeChatSalesAgentLocalAPI/1"

    def log_message(self, format, *args):
        return

    def _json(self, status: int, payload, extra_headers: Optional[Dict[str, str]] = None) -> None:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        headers = dict(extra_headers or {})
        self.send_response(status)
        self.send_header("Content-Type", headers.pop("Content-Type", "application/json; charset=utf-8"))
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(raw)

    def _problem(self, problem: APIProblem, instance: str, extra_headers: Optional[Dict[str, str]] = None) -> None:
        headers = dict(extra_headers or {})
        headers["Content-Type"] = "application/problem+json; charset=utf-8"
        self._json(
            problem.status,
            {
                "type": _problem_type(problem.code),
                "title": problem.title,
                "status": problem.status,
                "detail": problem.detail,
                "instance": instance,
                "code": problem.code,
            },
            headers,
        )

    def _rate_limit(self) -> Dict[str, str]:
        allowed, remaining, retry_after = self.server.rate_limiter.check(self.client_address[0])
        headers = {
            "X-RateLimit-Limit": str(self.server.rate_limiter.limit),
            "X-RateLimit-Remaining": str(remaining),
        }
        if not allowed:
            raise APIProblem(
                429,
                "RATE_LIMITED",
                "Rate limit exceeded",
                "请求过于频繁，请稍后重试。",
            )
        return headers

    def _authorize(self) -> None:
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise APIProblem(401, "UNAUTHORIZED", "Unauthorized", "需要 Bearer token。")
        supplied = authorization[7:].strip()
        if not supplied or not hmac.compare_digest(supplied, self.server.token):
            raise APIProblem(401, "UNAUTHORIZED", "Unauthorized", "Bearer token 无效。")

    def _body(self) -> Dict:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise APIProblem(411, "LENGTH_REQUIRED", "Length required", "请求必须包含 Content-Length。")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise APIProblem(400, "LENGTH_INVALID", "Invalid length", "Content-Length 无效。") from exc
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise APIProblem(413, "REQUEST_TOO_LARGE", "Request too large", "请求体超过 1 MiB 限制。")
        if self.headers.get_content_type() != "application/json":
            raise APIProblem(415, "MEDIA_TYPE_INVALID", "Unsupported media type", "请求体必须是 application/json。")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise APIProblem(400, "JSON_INVALID", "Invalid JSON", "请求体不是有效 JSON。") from exc
        if not isinstance(value, dict):
            raise APIProblem(422, "BODY_INVALID", "Invalid request", "请求体必须是 JSON 对象。")
        return value

    def _account(self) -> str:
        return validate_account_binding(self.server.db_path, self.server.chatlog_addr)

    def do_GET(self):
        path = urlsplit(self.path)
        try:
            rate_headers = self._rate_limit()
            if path.path == "/v1/health":
                self._json(200, {"status": "ok", "service": "wechat-sales-agent-local-api"}, rate_headers)
                return
            if path.path == "/openapi.json":
                spec_path = Path(__file__).with_name("local_api_openapi.json")
                self._json(200, json.loads(spec_path.read_text(encoding="utf-8")), rate_headers)
                return
            self._authorize()
            if path.path == "/v1/status":
                account_id = self._account()
                health = ChatlogClient(self.server.chatlog_addr).health()
                self._json(200, {"status": "ready", "active_account": account_id, "chatlog": health}, rate_headers)
                return
            if path.path == "/v1/dashboard":
                self._account()
                query = parse_qs(path.query)
                result = load_dashboard(
                    addr=self.server.chatlog_addr,
                    time_range=query.get("time_range", ["today"])[0],
                    private_chat=query.get("private_chat", [""])[0],
                    group_chat=query.get("group_chat", [""])[0],
                )
                self._json(200, result, rate_headers)
                return
            if path.path == "/v1/conversations":
                self._account()
                query = parse_qs(path.query)
                limit = _integer_query(query, "limit", DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)
                offset = _decode_cursor(query.get("cursor", [""])[0])
                rows = list_sessions(self.server.chatlog_addr, 5000)
                page = rows[offset : offset + limit]
                next_offset = offset + len(page)
                self._json(200, {
                    "data": page,
                    "pagination": {
                        "limit": limit,
                        "next_cursor": _encode_cursor(next_offset) if next_offset < len(rows) else None,
                        "has_next": next_offset < len(rows),
                    },
                }, rate_headers)
                return
            if path.path == "/v1/messages":
                self._account()
                query = parse_qs(path.query)
                chat = query.get("chat", [""])[0]
                if not chat.strip():
                    raise APIProblem(400, "CHAT_REQUIRED", "Chat required", "chat 查询参数不能为空。")
                limit = _integer_query(query, "limit", DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)
                offset = _decode_cursor(query.get("cursor", [""])[0])
                if offset + limit > 1000:
                    raise APIProblem(400, "CURSOR_LIMIT_EXCEEDED", "Cursor limit exceeded", "消息分页最多读取最近 1000 条匹配结果。")
                since = _integer_query(query, "since", 1, 1, 9999999999)
                until = _integer_query(query, "until", int(time.time()) + 1, 2, 9999999999)
                result = search_messages(
                    chat=chat,
                    since=since,
                    until=until,
                    keyword=query.get("keyword", [""])[0],
                    msg_type=query.get("msg_type", [""])[0],
                    sub_type=query.get("sub_type", [""])[0],
                    direction=query.get("direction", ["all"])[0],
                    limit=offset + limit,
                    addr=self.server.chatlog_addr,
                )
                page = result["messages"][offset : offset + limit]
                next_offset = offset + len(page)
                has_next = next_offset < min(result["matched_total"], 1000)
                self._json(200, {
                    "chat": result["chat"],
                    "matched_total": result["matched_total"],
                    "data": page,
                    "pagination": {
                        "limit": limit,
                        "next_cursor": _encode_cursor(next_offset) if has_next else None,
                        "has_next": has_next,
                    },
                }, rate_headers)
                return
            operation_prefix = "/v1/operations/"
            if path.path.startswith(operation_prefix):
                account_id = self._account()
                operation_id = path.path[len(operation_prefix) :]
                if not operation_id or "/" in operation_id:
                    raise APIProblem(404, "NOT_FOUND", "Not found", "资源不存在。")
                operation = self.server.operation_queue.get(operation_id)
                if operation is None:
                    raise APIProblem(404, "OPERATION_NOT_FOUND", "Operation not found", "分析操作不存在。")
                if operation["account_id"] != account_id:
                    raise APIProblem(409, "ACCOUNT_MISMATCH", "Account mismatch", "分析操作不属于当前微信账号。")
                self._json(200, operation, rate_headers)
                return
            raise APIProblem(404, "NOT_FOUND", "Not found", "资源不存在。")
        except APIProblem as exc:
            headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else {}
            if exc.status == 429:
                headers["Retry-After"] = "60"
            self._problem(exc, path.path, headers)
        except ChatlogError as exc:
            self._problem(APIProblem(503, exc.code, "Chatlog error", exc.message), path.path)
        except Exception:
            self._problem(APIProblem(500, "INTERNAL_ERROR", "Internal error", "请求处理失败。"), path.path)

    def do_POST(self):
        path = urlsplit(self.path)
        try:
            rate_headers = self._rate_limit()
            self._authorize()
            if path.path != "/v1/analyses":
                raise APIProblem(404, "NOT_FOUND", "Not found", "资源不存在。")
            account_id = self._account()
            idempotency_key = self.headers.get("Idempotency-Key", "").strip()
            if not idempotency_key or len(idempotency_key) > 200:
                raise APIProblem(400, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency key required", "必须提供不超过 200 字符的 Idempotency-Key。")
            payload = self._body()
            question = payload.get("question")
            if not isinstance(question, str) or not question.strip():
                raise APIProblem(422, "QUESTION_REQUIRED", "Question required", "question 必须是非空字符串。")
            allowed = {"question", "session_id", "task_type", "timeout"}
            if set(payload) - allowed:
                raise APIProblem(422, "FIELD_UNKNOWN", "Unknown field", "请求包含不支持的字段。")
            payload["question"] = question.strip()
            timeout = payload.get("timeout", 120)
            if isinstance(timeout, bool) or not isinstance(timeout, int) or not 10 <= timeout <= 600:
                raise APIProblem(422, "TIMEOUT_INVALID", "Invalid timeout", "timeout 必须在 10 到 600 秒之间。")
            for name in ("session_id", "task_type"):
                if name in payload and not isinstance(payload[name], str):
                    raise APIProblem(422, "FIELD_INVALID", "Invalid field", "%s 必须是字符串。" % name)
            operation, _created = self.server.operation_queue.submit(idempotency_key, payload, account_id)
            headers = dict(rate_headers)
            headers["Location"] = "/v1/operations/%s" % operation["id"]
            self._json(202, operation, headers)
        except APIProblem as exc:
            headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else {}
            if exc.status == 429:
                headers["Retry-After"] = "60"
            self._problem(exc, path.path, headers)
        except Exception:
            self._problem(APIProblem(500, "INTERNAL_ERROR", "Internal error", "请求处理失败。"), path.path)


def _load_token() -> str:
    try:
        token = KeychainStore(LOCAL_API_KEYCHAIN_SERVICE).get(LOCAL_API_KEYCHAIN_ACCOUNT)
    except ChatlogError as exc:
        raise SystemExit("本机 API token 尚未创建，请先运行 token 命令。") from exc
    if not token:
        raise SystemExit("本机 API token 为空，请重新生成。")
    return token


def token_command(rotate: bool = False) -> str:
    store = KeychainStore(LOCAL_API_KEYCHAIN_SERVICE)
    if not rotate:
        try:
            token = store.get(LOCAL_API_KEYCHAIN_ACCOUNT)
            if token:
                return token
        except ChatlogError:
            pass
    token = secrets.token_urlsafe(32)
    store.put_and_verify(LOCAL_API_KEYCHAIN_ACCOUNT, token)
    return token


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WeChat Customer Analysis local REST API")
    subparsers = parser.add_subparsers(dest="command", required=True)
    token = subparsers.add_parser("token", help="create or display the local Bearer token")
    token.add_argument("--rotate", action="store_true", help="replace the existing token")
    serve = subparsers.add_parser("serve", help="serve the API on 127.0.0.1")
    serve.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1",))
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--db", default=DEFAULT_DB)
    serve.add_argument("--chatlog-addr", default="127.0.0.1:5030")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "token":
        print(token_command(args.rotate))
        return 0
    token = _load_token()
    server = LocalAPIServer((args.host, args.port), token, args.db, args.chatlog_addr)
    print("Local API listening on http://127.0.0.1:%s" % server.server_address[1], flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
