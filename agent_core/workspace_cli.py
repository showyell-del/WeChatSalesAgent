import argparse
import json

from .events import emit, event
from .workspace_service import WorkspaceError, load_snapshot, workspace_readiness


def command_snapshot(args):
    try:
        snapshot = load_snapshot(args.db, args.account_id)
        print(json.dumps(snapshot, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, WorkspaceError) as exc:
        code = exc.code if isinstance(exc, WorkspaceError) else "WORKSPACE_READ_FAILED"
        message = exc.message if isinstance(exc, WorkspaceError) else str(exc)
        emit(event("workspace_snapshot", "failed", code, message))
        return 1


def command_readiness(args):
    try:
        print(json.dumps(workspace_readiness(args.db), ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, WorkspaceError) as exc:
        code = exc.code if isinstance(exc, WorkspaceError) else "WORKSPACE_READ_FAILED"
        message = exc.message if isinstance(exc, WorkspaceError) else str(exc)
        emit(event("workspace_readiness", "failed", code, message))
        return 1


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="runtime/agent_state.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)
    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--account-id", default="")
    snapshot.set_defaults(func=command_snapshot)
    sub.add_parser("readiness").set_defaults(func=command_readiness)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
