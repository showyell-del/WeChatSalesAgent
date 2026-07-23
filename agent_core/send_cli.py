import argparse
import json

from .events import emit, event
from .send_store import SendError, SendStore


def command_create(args):
    store = SendStore(args.db)
    try:
        batch = store.create_batch(
            account_id=args.account_id,
            message_text=args.text,
            customer_ids=args.customer_id,
            bands=args.band,
            attachments=args.attachment,
        )
        emit(event("send_batch", "passed", "SEND_BATCH_CREATED", "Send batch created.", {
            "batch_id": batch["batch_id"],
            "total": str(batch["total"]),
            "status": batch["status"],
        }))
        print(json.dumps(batch, ensure_ascii=False, sort_keys=True))
        return 0
    except SendError as exc:
        emit(event("send_batch", "failed", exc.code, exc.message))
        return 1
    finally:
        store.close()


def command_list(args):
    store = SendStore(args.db)
    try:
        print(json.dumps(store.list_batches(args.account_id), ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        store.close()


def command_show(args):
    store = SendStore(args.db)
    try:
        print(json.dumps(store.batch(args.batch_id), ensure_ascii=False, sort_keys=True))
        return 0
    except SendError as exc:
        emit(event("send_batch", "failed", exc.code, exc.message))
        return 1
    finally:
        store.close()


def command_dispatch(args):
    store = SendStore(args.db)
    try:
        batch = store.block_batch(
            args.batch_id,
            "NATIVE_SEND_ADAPTER_NOT_CERTIFIED",
            "Native text/image/video/file sending is not fully certified for this WeChat session.",
        )
        emit(event("send_dispatch", "blocked", "NATIVE_SEND_ADAPTER_NOT_CERTIFIED", batch["blocked_message"], {
            "batch_id": batch["batch_id"],
            "total": str(batch["total"]),
        }))
        print(json.dumps(batch, ensure_ascii=False, sort_keys=True))
        return 2
    except SendError as exc:
        emit(event("send_dispatch", "failed", exc.code, exc.message))
        return 1
    finally:
        store.close()


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="runtime/agent_state.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("--account-id", required=True)
    create.add_argument("--text", required=True)
    create.add_argument("--customer-id", action="append", default=[])
    create.add_argument("--band", action="append", default=[])
    create.add_argument("--attachment", action="append", default=[])
    create.set_defaults(func=command_create)

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--account-id", default="")
    list_cmd.set_defaults(func=command_list)

    show = sub.add_parser("show")
    show.add_argument("--batch-id", required=True)
    show.set_defaults(func=command_show)

    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("--batch-id", required=True)
    dispatch.set_defaults(func=command_dispatch)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
