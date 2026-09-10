import argparse
import hashlib
import sqlite3

from .corpus_store import evidence_id
from .events import emit, event


def validate(db_path: str, account_id: str) -> dict:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        run = connection.execute(
            "SELECT * FROM corpus_runs WHERE account_id=? AND status='published' ORDER BY published_at DESC LIMIT 1",
            (account_id,),
        ).fetchone()
        if run is None:
            raise RuntimeError("PUBLISHED_CORPUS_MISSING")
        corpus_id = run["corpus_id"]
        session_count = connection.execute(
            "SELECT count(*) FROM sessions WHERE generation_id=?",
            (run["generation_id"],),
        ).fetchone()[0]
        conversation_count = connection.execute(
            "SELECT count(*) FROM corpus_conversations WHERE corpus_id=?", (corpus_id,)
        ).fetchone()[0]
        if conversation_count != session_count:
            raise RuntimeError("CORPUS_SESSION_COUNT_MISMATCH")

        eligible = connection.execute(
            "SELECT count(*) FROM corpus_conversations WHERE corpus_id=? AND status='eligible'",
            (corpus_id,),
        ).fetchone()[0]
        bad_eligible = connection.execute(
            "SELECT count(*) FROM corpus_conversations WHERE corpus_id=? AND status='eligible' AND (inbound_count=0 OR outbound_count=0 OR username LIKE '%@chatroom')",
            (corpus_id,),
        ).fetchone()[0]
        if bad_eligible:
            raise RuntimeError("INELIGIBLE_CONVERSATION_PUBLISHED")
        eligible_without_evidence = connection.execute(
            """SELECT count(*) FROM corpus_conversations cc
               WHERE cc.corpus_id=? AND cc.status='eligible' AND NOT EXISTS (
                   SELECT 1 FROM corpus_evidence ce JOIN evidence e ON e.evidence_id=ce.evidence_id
                   WHERE ce.corpus_id=cc.corpus_id AND e.username=cc.username
               )""",
            (corpus_id,),
        ).fetchone()[0]
        if eligible_without_evidence:
            raise RuntimeError("ELIGIBLE_CONVERSATION_WITHOUT_EVIDENCE")

        rows = connection.execute(
            "SELECT e.* FROM corpus_evidence ce JOIN evidence e ON e.evidence_id=ce.evidence_id WHERE ce.corpus_id=?",
            (corpus_id,),
        ).fetchall()
        for row in rows:
            item = dict(row)
            if (
                item["account_id"] != account_id
                or item["generation_id"] != run["generation_id"]
            ):
                raise RuntimeError("CROSS_SCOPE_EVIDENCE")
            actual_hash = hashlib.sha256(item["content"].encode("utf-8")).hexdigest()
            if actual_hash != item["content_sha256"]:
                raise RuntimeError("EVIDENCE_CONTENT_HASH_MISMATCH")
            reconstructed = {
                "local_id": item["local_id"],
                "is_self": bool(item["is_self"]),
                "sender": item["sender"],
                "timestamp": item["timestamp"],
                "content": item["content"],
            }
            if (
                evidence_id(
                    account_id, run["generation_id"], item["username"], reconstructed
                )
                != item["evidence_id"]
            ):
                raise RuntimeError("EVIDENCE_ID_MISMATCH")

        orphan_facts = connection.execute(
            "SELECT count(*) FROM extracted_facts f LEFT JOIN evidence e ON e.evidence_id=f.evidence_id WHERE f.corpus_id=? AND e.evidence_id IS NULL",
            (corpus_id,),
        ).fetchone()[0]
        self_facts = connection.execute(
            "SELECT count(*) FROM extracted_facts f JOIN evidence e ON e.evidence_id=f.evidence_id WHERE f.corpus_id=? AND e.is_self=1",
            (corpus_id,),
        ).fetchone()[0]
        if orphan_facts or self_facts:
            raise RuntimeError("FACT_EVIDENCE_BINDING_INVALID")
        facts = connection.execute(
            "SELECT count(*) FROM extracted_facts WHERE corpus_id=?", (corpus_id,)
        ).fetchone()[0]
        return {
            "corpus_id": corpus_id,
            "sessions": session_count,
            "eligible": eligible,
            "excluded": conversation_count - eligible,
            "evidence": len(rows),
            "facts": facts,
        }
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="runtime/agent_state.sqlite3")
    parser.add_argument("--account-id", required=True)
    args = parser.parse_args(argv)
    try:
        result = validate(args.db, args.account_id)
    except Exception as exc:
        emit(event("corpus_integrity", "failed", "CORPUS_INTEGRITY_FAILED", str(exc)))
        return 1
    emit(
        event(
            "corpus_integrity",
            "passed",
            "CORPUS_INTEGRITY_OK",
            "Published corpus passed scope, hash, direction, and relation checks.",
            {key: str(value) for key, value in result.items()},
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
