import argparse
import json

from .chatlog_client import ChatlogError
from .events import emit, event
from .message_search import list_sessions, search_messages


def command_sessions(args):
    try:
        print(json.dumps({"sessions": list_sessions(args.addr, args.limit)}, ensure_ascii=False, sort_keys=True))
        return 0
    except ChatlogError as exc:
        emit(event("message_sessions", "failed", exc.code, exc.message))
        return 1


def command_search(args):
    try:
        result = search_messages(
            chat=args.chat,
            since=args.since,
            until=args.until,
            keyword=args.keyword,
            msg_type=args.msg_type,
            sub_type=args.sub_type,
            direction=args.direction,
            limit=args.limit,
            addr=args.addr,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except ChatlogError as exc:
        emit(event("message_search", "failed", exc.code, exc.message))
        return 1


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--addr", default="127.0.0.1:5030")
    sub = parser.add_subparsers(dest="command", required=True)
    sessions = sub.add_parser("sessions")
    sessions.add_argument("--limit", type=int, default=500)
    sessions.set_defaults(func=command_sessions)
    search = sub.add_parser("search")
    search.add_argument("--chat", required=True)
    search.add_argument("--since", type=int, required=True)
    search.add_argument("--until", type=int, required=True)
    search.add_argument("--keyword", default="")
    search.add_argument("--msg-type", default="")
    search.add_argument("--sub-type", default="")
    search.add_argument("--direction", choices=("all", "self", "other"), default="all")
    search.add_argument("--limit", type=int, default=200)
    search.set_defaults(func=command_search)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
