from typing import Dict, List

from .chatlog_client import ChatlogClient, ChatlogError


def list_sessions(addr: str = "127.0.0.1:5030", limit: int = 500) -> List[Dict]:
    if limit <= 0 or limit > 5000:
        raise ChatlogError("MESSAGE_SEARCH_LIMIT_INVALID", "Session limit must be 1-5000.")
    sessions = ChatlogClient(addr=addr).all_sessions(page_size=limit)
    result = []
    for item in sessions:
        username = str(item.get("username") or "").strip()
        if not username:
            continue
        result.append(
            {
                "username": username,
                "display_name": str(item.get("chat") or username),
                "is_group": bool(item.get("is_group")),
                "time": str(item.get("time") or ""),
            }
        )
    return result


def search_messages(
    chat: str,
    since: int,
    until: int,
    keyword: str = "",
    msg_type: str = "",
    sub_type: str = "",
    direction: str = "all",
    limit: int = 200,
    addr: str = "127.0.0.1:5030",
) -> Dict:
    chat = chat.strip()
    if not chat:
        raise ChatlogError("MESSAGE_SEARCH_CHAT_REQUIRED", "A chat must be selected.")
    if since <= 0 or until <= since:
        raise ChatlogError("MESSAGE_SEARCH_TIME_INVALID", "The search time range is invalid.")
    if limit <= 0 or limit > 1000:
        raise ChatlogError("MESSAGE_SEARCH_LIMIT_INVALID", "Message limit must be 1-1000.")
    if direction not in {"all", "self", "other"}:
        raise ChatlogError("MESSAGE_SEARCH_DIRECTION_INVALID", "Message direction is invalid.")

    directions = (False, True) if direction == "all" else (direction == "self",)
    client = ChatlogClient(addr=addr)
    merged = []
    matched_total = 0
    for is_self in directions:
        query = {
            "chat": chat,
            "since": str(since),
            "until": str(until),
            "limit": "1",
            "offset": "0",
            "is_self": "true" if is_self else "false",
            "format": "json",
        }
        if keyword.strip():
            query["keyword"] = keyword.strip()
        if msg_type.strip():
            query["msg_type"] = msg_type.strip()
        if sub_type.strip():
            query["sub_type"] = sub_type.strip()
        count_data = client.get_json("/api/v1/history", query)
        if not isinstance(count_data, dict) or not isinstance(count_data.get("messages"), list):
            raise ChatlogError(
                "CHATLOG_HISTORY_INVALID",
                "Chatlog history response did not contain a messages array.",
            )
        direction_total = int(count_data.get("total_count") or 0)
        matched_total += direction_total
        if direction_total == 0:
            continue
        query["limit"] = str(min(limit, direction_total))
        query["offset"] = str(max(direction_total - limit, 0))
        data = client.get_json("/api/v1/history", query)
        messages = data.get("messages") if isinstance(data, dict) else None
        if not isinstance(messages, list):
            raise ChatlogError(
                "CHATLOG_HISTORY_INVALID",
                "Chatlog history response did not contain a messages array.",
            )
        for item in messages:
            merged.append(
                {
                    "timestamp": int(item.get("timestamp") or 0),
                    "time": str(item.get("time") or ""),
                    "direction": "我方" if is_self else "对方",
                    "sender": str(item.get("sender") or ""),
                    "type": str(item.get("type") or ""),
                    "content": str(item.get("content") or ""),
                    "local_id": str(item.get("local_id") or ""),
                }
            )
    merged.sort(
        key=lambda item: (item["timestamp"], item["local_id"], item["direction"]),
        reverse=True,
    )
    return {
        "chat": chat,
        "matched_total": matched_total,
        "count": min(len(merged), limit),
        "messages": merged[:limit],
    }
