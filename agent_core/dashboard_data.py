from typing import Dict, List

from .chatlog_client import ChatlogClient, ChatlogError
from .corpus_builder import static_exclusion
from .dashboard_trend import daily_trend


def _stats(client: ChatlogClient, username: str, time_range: str) -> Dict:
    data = client.get_json(
        "/api/v1/stats",
        {"format": "json", "chat": username, "time": time_range},
    )
    if not isinstance(data, dict):
        raise ChatlogError("CHATLOG_STATS_INVALID", "Chatlog stats response is invalid.")
    return data


def _peak_hour(stats: Dict) -> int:
    rows = stats.get("by_hour") if isinstance(stats.get("by_hour"), list) else []
    peak = max(rows, key=lambda row: int(row.get("count") or 0), default={"hour": 0})
    return int(peak.get("hour") or 0)


def _type_summary(rows) -> str:
    valid = [
        (str(row.get("type") or "unknown"), int(row.get("count") or 0))
        for row in rows if isinstance(row, dict) and int(row.get("count") or 0) > 0
    ]
    total = sum(count for _, count in valid)
    if not total:
        return "暂无消息类型"
    return " · ".join("%s %d%%" % (name, round(count * 100 / total)) for name, count in valid)


def load_dashboard(
    addr: str = "127.0.0.1:5030",
    time_range: str = "today",
    private_chat: str = "",
    group_chat: str = "",
) -> Dict:
    if time_range not in {"today", "last-1d", "last-30d", "all"}:
        raise ChatlogError("DASHBOARD_TIME_RANGE_INVALID", "Dashboard time range is invalid.")
    stats_time_range = "last-1d" if time_range in {"today", "last-1d"} else time_range
    client = ChatlogClient(addr=addr, timeout=180)
    sessions = client.all_sessions(page_size=500)
    if not sessions:
        raise ChatlogError("CHATLOG_SESSIONS_EMPTY", "未读取到会话，请先连接并同步微信。")
    private_sessions = [row for row in sessions if not static_exclusion(row)]
    private_session = next((row for row in private_sessions if row.get("username") == private_chat), None)
    if private_session is None and private_sessions:
        private_session = private_sessions[0]
    all_group_sessions = [row for row in sessions if row.get("is_group")]
    private_stats = _stats(client, private_session["username"], stats_time_range) if private_session else {}
    group_stats: List[Dict] = []
    selected_group_stats = {}
    for session in all_group_sessions:
        stats = _stats(client, str(session.get("username") or ""), stats_time_range)
        if session.get("username") == group_chat or (not group_chat and not selected_group_stats):
            selected_group_stats = dict(stats)
            selected_group_stats["type_summary"] = _type_summary(stats.get("by_type") or [])
        if int(stats.get("total") or 0) <= 0:
            continue
        top_sender = (stats.get("top_senders") or [{}])[0]
        group_stats.append(
            {
                "chat": str(stats.get("chat") or session.get("chat") or session.get("username") or ""),
                "username": str(session.get("username") or ""),
                "total": int(stats.get("total") or 0),
                "active_senders": int(stats.get("active_senders") or 0),
                "active_days": int(stats.get("active_days") or 0),
                "peak_hour": _peak_hour(stats),
                "top_sender": str(top_sender.get("sender") or ""),
                "top_sender_count": int(top_sender.get("count") or 0),
                "by_type": stats.get("by_type") or [],
                "type_summary": _type_summary(stats.get("by_type") or []),
                "by_hour": stats.get("by_hour") or [],
                "top_senders": stats.get("top_senders") or [],
            }
        )
    speakers = {}
    for group in group_stats:
        for row in group["top_senders"]:
            name = str(row.get("sender") or "").strip()
            if not name:
                continue
            current = speakers.setdefault(name, {"name": name, "count": 0, "groups": set()})
            current["count"] += int(row.get("count") or 0)
            current["groups"].add(group["chat"])
    leaderboard = [
        {"name": row["name"], "count": row["count"], "group_count": len(row["groups"]), "group": next(iter(row["groups"]), "")}
        for row in speakers.values()
    ]
    leaderboard.sort(key=lambda row: (-row["count"], row["name"]))
    databases = client.databases()
    daily = daily_trend(client, databases)
    group_total = sum(row["total"] for row in group_stats)
    active_sender_slots = sum(row["active_senders"] for row in group_stats)
    message_type_counts = {}
    hour_counts = {hour: 0 for hour in range(24)}
    for group in group_stats:
        for row in group["by_type"]:
            name = str(row.get("type") or "unknown")
            message_type_counts[name] = message_type_counts.get(name, 0) + int(row.get("count") or 0)
        for row in group["by_hour"]:
            hour = int(row.get("hour") or 0)
            if 0 <= hour <= 23:
                hour_counts[hour] += int(row.get("count") or 0)
    return {
        "private": private_stats,
        "selected_group": selected_group_stats,
        "private_sessions": private_sessions,
        "group_sessions": all_group_sessions,
        "time_range": time_range,
        "groups": group_stats,
        "leaderboard": leaderboard[:15],
        "overview": {
            "messages": group_total,
            "groups": len(group_stats),
            "active_sender_slots": active_sender_slots,
        },
        "daily": daily,
        "message_types": [
            {"type": name, "count": count}
            for name, count in sorted(message_type_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "by_hour": [{"hour": hour, "count": hour_counts[hour]} for hour in range(24)],
        "databases": [{"kind": kind, "path": path} for kind, paths in databases.items() for path in paths],
    }
