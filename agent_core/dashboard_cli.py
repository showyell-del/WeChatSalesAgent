import argparse
import json

from .chatlog_client import ChatlogError
from .dashboard_data import load_dashboard
from .events import emit, event


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--addr", default="127.0.0.1:5030")
    parser.add_argument("--time-range", default="today")
    parser.add_argument("--private-chat", default="")
    parser.add_argument("--group-chat", default="")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(load_dashboard(args.addr, args.time_range, args.private_chat, args.group_chat), ensure_ascii=False, sort_keys=True))
        return 0
    except ChatlogError as exc:
        emit(event("dashboard", "failed", exc.code, exc.message))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
