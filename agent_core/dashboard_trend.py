import datetime
import re

from .chatlog_client import ChatlogError


def daily_trend(client, databases):
    today = datetime.date.today()
    days = [today - datetime.timedelta(days=n) for n in range(29, -1, -1)]
    counts = {day.isoformat(): 0 for day in days}
    since = int(datetime.datetime.combine(days[0], datetime.time()).timestamp())
    until = int(datetime.datetime.combine(today + datetime.timedelta(days=1), datetime.time()).timestamp())
    files = [path for path in databases.get("message", []) if not path.endswith("_fts.db")]
    if not files:
        raise ChatlogError("CHATLOG_MESSAGE_DATABASES_EMPTY", "No message databases available.")
    for path in files:
        tables = client.get_json("/api/v1/db/tables", {"group": "message", "file": path})
        if not isinstance(tables, list):
            raise ChatlogError("CHATLOG_TABLES_INVALID", "Message table list is invalid.")
        names = [name for name in tables if isinstance(name, str) and re.fullmatch(r"Msg_[0-9a-f]{32}", name)]
        for offset in range(0, len(names), 100):
            statements = [
                'SELECT strftime(\'%%Y-%%m-%%d\',create_time,\'unixepoch\',\'localtime\') AS date, COUNT(*) AS count '
                'FROM "%s" WHERE create_time >= %d AND create_time < %d GROUP BY date' % (name, since, until)
                for name in names[offset:offset + 100]
            ]
            rows = client.get_json("/api/v1/db/query", {
                "group": "message", "file": path,
                "sql": "SELECT date, SUM(count) AS count FROM (" + " UNION ALL ".join(statements) + ") GROUP BY date",
            })
            if not isinstance(rows, list):
                raise ChatlogError("CHATLOG_TREND_INVALID", "Daily message counts are invalid.")
            for row in rows:
                if row.get("date") not in counts or not isinstance(row.get("count"), int) or row["count"] < 0:
                    raise ChatlogError("CHATLOG_TREND_INVALID", "Daily message count is outside the requested range.")
                counts[row["date"]] += row["count"]
    return [{"date": day, "count": count} for day, count in counts.items()]
