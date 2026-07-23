import argparse
import json

from .events import emit, event
from .send_certification import certified_capabilities, uncertified_required_types
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
        current = store.batch(args.batch_id)
        missing = uncertified_required_types(store.conn, current)
        if missing:
            message = "Native send adapter certification is missing for: " + ", ".join(missing)
            batch = store.block_batch(args.batch_id, "NATIVE_SEND_ADAPTER_NOT_CERTIFIED", message)
            emit(event("send_dispatch", "blocked", "NATIVE_SEND_ADAPTER_NOT_CERTIFIED", batch["blocked_message"], {
                "batch_id": batch["batch_id"],
                "total": str(batch["total"]),
                "missing_types": ",".join(missing),
            }))
            print(json.dumps(batch, ensure_ascii=False, sort_keys=True))
            return 2
        batch = store.block_batch(
            args.batch_id,
            "NATIVE_SEND_SESSION_OWNER_NOT_IMPLEMENTED",
            "Native send session owner is not implemented for certified dispatch.",
        )
        emit(event("send_dispatch", "blocked", "NATIVE_SEND_SESSION_OWNER_NOT_IMPLEMENTED", batch["blocked_message"], {
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


def command_capabilities(args):
    store = SendStore(args.db)
    try:
        print(json.dumps(certified_capabilities(store.conn), ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        store.close()


def command_cancel(args):
    store = SendStore(args.db)
    try:
        if args.customer_id:
            batch = store.cancel_recipient(args.batch_id, args.customer_id)
        else:
            batch = store.cancel_batch(args.batch_id)
        emit(event("send_batch", "passed", "SEND_BATCH_CANCELLED", "Send batch recipients cancelled.", {
            "batch_id": batch["batch_id"],
            "status": batch["status"],
        }))
        print(json.dumps(batch, ensure_ascii=False, sort_keys=True))
        return 0
    except SendError as exc:
        emit(event("send_batch", "failed", exc.code, exc.message))
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

    capabilities = sub.add_parser("capabilities")
    capabilities.set_defaults(func=command_capabilities)

    show = sub.add_parser("show")
    show.add_argument("--batch-id", required=True)
    show.set_defaults(func=command_show)

    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("--batch-id", required=True)
    dispatch.set_defaults(func=command_dispatch)

    cancel = sub.add_parser("cancel")
    cancel.add_argument("--batch-id", required=True)
    cancel.add_argument("--customer-id", default="")
    cancel.set_defaults(func=command_cancel)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
