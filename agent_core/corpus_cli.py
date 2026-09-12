import argparse
import time

from .chatlog_client import ChatlogError
from .corpus_builder import build_corpus
from .events import emit, event


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="runtime/agent_state.sqlite3")
    parser.add_argument("--addr", default="127.0.0.1:5030")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--days", type=int, default=3650)
    parser.add_argument("--all-history", action="store_true")
    parser.add_argument("--page-size", type=int, default=500)
    args = parser.parse_args(argv)
    until_ts = int(time.time()) + 86400
    since_ts = 0 if args.all_history else until_ts - args.days * 86400
    try:
        result = build_corpus(
            args.db, args.account_id, since_ts, until_ts, args.addr, args.page_size
        )
    except ChatlogError as exc:
        emit(event("corpus", "failed", exc.code, exc.message))
        return 1
    except Exception as exc:
        emit(event("corpus", "failed", "CORPUS_BUILD_FAILED", str(exc)))
        return 1
    emit(
        event(
            "corpus",
            "passed",
            "CORPUS_PUBLISHED",
            "Private-chat evidence corpus published.",
            {key: str(value) for key, value in result.items()},
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
