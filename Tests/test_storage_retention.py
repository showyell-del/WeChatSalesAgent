import os
import sqlite3
import tempfile
import unittest

from agent_core.corpus_store import CorpusStore
from agent_core.sync_store import SyncStore


class StorageRetentionTests(unittest.TestCase):
    def test_foreign_key_children_are_indexed_for_bulk_retention_cleanup(self):
        connection = sqlite3.connect(":memory:")
        CorpusStore(connection)
        facts = {row[1] for row in connection.execute("PRAGMA index_list('extracted_facts')")}
        links = {row[1] for row in connection.execute("PRAGMA index_list('corpus_evidence')")}
        self.assertIn("facts_by_evidence", facts)
        self.assertIn("corpus_evidence_by_evidence", links)
        connection.close()

    def test_publishing_full_history_can_remove_superseded_account_corpora(self):
        handle, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        try:
            sync = SyncStore(path)
            sync.upsert_account("account", "/data/account", "verified")
            sync.conn.execute(
                "INSERT INTO generations VALUES(?,?,?,?,?,?,?)",
                ("old-generation", "account", "old", 1, 2, None, None),
            )
            sync.conn.execute(
                "INSERT INTO generations VALUES(?,?,?,?,?,?,?)",
                ("new-generation", "account", "published", 3, 4, None, None),
            )
            corpus = CorpusStore(sync.conn)
            sync.conn.execute(
                "INSERT INTO corpus_runs VALUES(?,?,?,?,?,?,?,?,?,?)",
                ("old-corpus", "old-generation", "account", 0, 10, "old", 1, 2, None, None),
            )
            sync.conn.execute(
                "INSERT INTO corpus_runs VALUES(?,?,?,?,?,?,?,?,?,?)",
                ("new-corpus", "new-generation", "account", 0, 20, "published", 3, 4, None, None),
            )
            sync.conn.execute(
                "INSERT INTO corpus_conversations VALUES(?,?,?,?,?,?,?,?)",
                ("old-corpus", "old-user", "旧联系人", "eligible", None, 1, 1, 9),
            )
            sync.conn.execute(
                "INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                ("old-evidence", "old-corpus", "account", "old-generation", "old-user", 1, 0, "旧联系人", 9, "text", "旧消息", "hash"),
            )
            sync.conn.execute("INSERT INTO corpus_evidence VALUES(?,?)", ("old-corpus", "old-evidence"))
            sync.conn.commit()

            self.assertEqual(corpus.purge_old_runs("account", "new-corpus"), 1)
            self.assertEqual(sync.conn.execute("SELECT count(*) FROM corpus_runs WHERE corpus_id='old-corpus'").fetchone()[0], 0)
            self.assertEqual(sync.conn.execute("SELECT count(*) FROM evidence WHERE corpus_id='old-corpus'").fetchone()[0], 0)
            self.assertEqual(sync.conn.execute("SELECT count(*) FROM generations WHERE generation_id='old-generation'").fetchone()[0], 0)
            self.assertEqual(sync.conn.execute("SELECT count(*) FROM corpus_runs WHERE corpus_id='new-corpus'").fetchone()[0], 1)
            sync.close()
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
