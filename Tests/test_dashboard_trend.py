import datetime
import sqlite3
import unittest

from agent_core.dashboard_trend import daily_trend


class TrendTests(unittest.TestCase):
    def test_sql_aggregates_multiple_tables_and_zero_days(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        tables = ["Msg_" + c * 32 for c in "ab"]
        today = datetime.date.today()
        now = int(datetime.datetime.combine(today, datetime.time(12)).timestamp())
        for name in tables:
            db.execute('CREATE TABLE "%s" (create_time INTEGER)' % name)
            db.executemany('INSERT INTO "%s" VALUES (?)' % name, [(now,), (now - 86400,), (now - 40 * 86400,)])

        class Client:
            def get_json(self, endpoint, query):
                if endpoint.endswith("tables"):
                    return tables + ["Name2Id"]
                return [dict(row) for row in db.execute(query["sql"])]

        try:
            result = daily_trend(Client(), {"message": ["/message.db"]})
            self.assertEqual(len(result), 30)
            self.assertEqual(sum(row["count"] for row in result), 4)
            self.assertEqual(result[-1], {"date": today.isoformat(), "count": 2})
            self.assertEqual(result[0]["count"], 0)
        finally:
            db.close()
