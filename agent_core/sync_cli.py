import argparse
import os

from .chatlog_client import ChatlogClient, ChatlogError, derive_account_ids, iter_db_paths
from .chatlog_runtime import ChatlogRuntime, HEX_KEY, verify_runtime_account
from .events import emit, event
from .keychain import KeychainStore
from .sync_store import SyncStore


DEFAULT_DB = "runtime/agent_state.sqlite3"
DEFAULT_CHATLOG_BIN = "chatlog_2f54920_darwin_arm64/chatlog-darwin-arm64"


def data_root_for_account(db_map, account_id):
    for path in iter_db_paths(db_map):
        marker = "/xwechat_files/%s/" % account_id
        if marker in path:
            return path.split("/db_storage/", 1)[0]
    return ""


def command_health(args):
    client = ChatlogClient(args.addr, args.timeout)
    try:
        data = client.health()
    except ChatlogError as exc:
        emit(event("chatlog_health", "failed", exc.code, exc.message))
        return 1
    status = data.get("status", "")
    if status == "ok":
        emit(event("chatlog_health", "passed", "CHATLOG_HEALTH_OK", "Chatlog service is healthy.", {"addr": args.addr}))
        return 0
    emit(event("chatlog_health", "failed", "CHATLOG_HEALTH_NOT_OK", "Chatlog health did not return ok.", {"status": str(status)}))
    return 1


def command_discover(args):
    client = ChatlogClient(args.addr, args.timeout)
    try:
        db_map = client.databases()
    except ChatlogError as exc:
        emit(event("account_discovery", "failed", exc.code, exc.message))
        return 1
    account_ids = derive_account_ids(db_map)
    if not account_ids:
        emit(event("account_discovery", "failed", "ACCOUNT_PATH_NOT_FOUND", "No xwechat_files account id was found in Chatlog database paths."))
        return 1
    store = SyncStore(args.db)
    try:
        for account_id in account_ids:
            root = data_root_for_account(db_map, account_id)
            store.upsert_account(account_id, root, "discovered")
            emit(event("account_discovery", "passed", "ACCOUNT_DISCOVERED", "WeChat account discovered.", {
                "account_id": account_id,
                "data_root": root,
            }))
    finally:
        store.close()
    return 0


def command_accounts(args):
    runtime = ChatlogRuntime(args.chatlog_bin)
    try:
        accounts = runtime.list_accounts()
    except ChatlogError as exc:
        emit(event("account_list", "failed", exc.code, exc.message))
        return 1
    if not accounts:
        emit(event("account_list", "failed", "WECHAT_ACCOUNTS_EMPTY", "Chatlog has no running or historical accounts."))
        return 1
    for item in accounts:
        emit(event("account_list", "passed", "WECHAT_ACCOUNT_AVAILABLE", "WeChat account is available.", {
            "account_id": str(item.get("account", "")),
            "current": str(bool(item.get("current"))).lower(),
            "data_root": str(item.get("data_dir", "")),
        }))
    return 0


def prepare_account(client, runtime, store, account_id):
    db_map = client.databases()
    account_ids = derive_account_ids(db_map)
    if account_id not in account_ids:
        raise ChatlogError("ACCOUNT_NOT_IN_CHATLOG_DB_PATHS", "Selected account was not present in Chatlog database paths.")
    root = data_root_for_account(db_map, account_id)
    store.upsert_account(account_id, root, "connecting")
    runtime_status = runtime.status(account_id)
    if not HEX_KEY.fullmatch(str(runtime_status.get("data_key", ""))):
        runtime.obtain_key(account_id)
        runtime_status = runtime.status(account_id)
    data_key = str(runtime_status.get("data_key", ""))
    if not HEX_KEY.fullmatch(data_key):
        raise ChatlogError("DATABASE_KEY_MISSING", "Selected account does not have a valid database key.")
    KeychainStore().put_and_verify(account_id, data_key)
    runtime.decompress(account_id)
    runtime_status = runtime.status(account_id)
    verification = verify_runtime_account(runtime_status, account_id, db_map)
    store.mark_key_verified(account_id, len(verification["verified_databases"]))
    return db_map, root, verification


def command_connect(args):
    client = ChatlogClient(args.addr, args.timeout)
    runtime = ChatlogRuntime(args.chatlog_bin)
    store = SyncStore(args.db)
    account_id = args.account_id
    try:
        if not account_id:
            db_map = client.databases()
            account_ids = derive_account_ids(db_map)
            if len(account_ids) != 1:
                raise ChatlogError("ACCOUNT_SELECTION_REQUIRED", "Select exactly one WeChat account before connecting.")
            account_id = account_ids[0]
        _, _, verification = prepare_account(client, runtime, store, account_id)
        emit(event("account_connect", "passed", "ACCOUNT_KEY_AND_DATABASES_VERIFIED", "Account key and decrypted databases are ready.", {
            "account_id": account_id,
            "verified_databases": str(len(verification["verified_databases"])),
        }))
        return 0
    except ChatlogError as exc:
        emit(event("account_connect", "failed", exc.code, exc.message, {"account_id": account_id}))
        return 1
    finally:
        store.close()


def command_switch(args):
    runtime = ChatlogRuntime(args.chatlog_bin)
    try:
        accounts = runtime.list_accounts()
        available = {str(item.get("account", "")) for item in accounts}
        if args.account_id not in available:
            raise ChatlogError("HISTORICAL_ACCOUNT_NOT_FOUND", "Selected historical account is not available.")
        result = runtime.switch_account(args.account_id)
        if result.get("account") != args.account_id:
            raise ChatlogError("CHATLOG_ACCOUNT_MISMATCH", "Chatlog did not switch to the selected account.")
        emit(event("account_switch", "passed", "ACCOUNT_SWITCHED", "Historical WeChat account selected.", {
            "account_id": args.account_id,
        }))
        return 0
    except ChatlogError as exc:
        emit(event("account_switch", "failed", exc.code, exc.message, {"account_id": args.account_id}))
        return 1


def command_sync(args):
    client = ChatlogClient(args.addr, args.timeout)
    runtime = ChatlogRuntime(args.chatlog_bin)
    store = SyncStore(args.db)
    generation_id = None
    account_id = ""
    root = ""
    try:
        health = client.health()
        if health.get("status") != "ok":
            emit(event("sync", "failed", "CHATLOG_HEALTH_NOT_OK", "Chatlog health did not return ok."))
            return 1

        db_map = client.databases()
        account_ids = derive_account_ids(db_map)
        if not account_ids:
            emit(event("sync", "failed", "ACCOUNT_PATH_NOT_FOUND", "No account id was found in Chatlog database paths."))
            return 1
        account_id = args.account_id or account_ids[0]
        if account_id not in account_ids:
            emit(event("sync", "failed", "ACCOUNT_NOT_IN_CHATLOG_DB_PATHS", "Selected account was not present in Chatlog database paths.", {
                "account_id": account_id,
                "available": ",".join(account_ids),
            }))
            return 1

        db_map, root, verification = prepare_account(client, runtime, store, account_id)
        emit(event("database_key", "passed", "DATABASE_KEY_VERIFIED", "Database key and decrypted primary databases verified.", {
            "account_id": account_id,
            "verified_databases": str(len(verification["verified_databases"])),
        }))
        generation_id = store.create_generation(account_id)
        store.insert_db_files(generation_id, db_map)
        sessions = client.sessions(limit=args.limit, offset=0)
        if not sessions:
            store.fail_generation(generation_id, "CHATLOG_SESSIONS_EMPTY", "Chatlog returned no sessions.")
            store.upsert_account(account_id, root, "failed", "CHATLOG_SESSIONS_EMPTY", "Chatlog returned no sessions.")
            emit(event("sync", "failed", "CHATLOG_SESSIONS_EMPTY", "Chatlog returned no sessions.", {"generation_id": generation_id}))
            return 1

        session_count = store.insert_sessions(generation_id, sessions)
        store.publish_generation(generation_id, account_id)
        emit(event("sync", "passed", "GENERATION_PUBLISHED", "Fresh account-bound generation published.", {
            "account_id": account_id,
            "generation_id": generation_id,
            "session_count": str(session_count),
            "db_groups": str(len(db_map)),
        }))
        return 0
    except ChatlogError as exc:
        if generation_id:
            store.fail_generation(generation_id, exc.code, exc.message)
        if account_id:
            store.upsert_account(account_id, root, "failed", exc.code, exc.message)
        emit(event("sync", "failed", exc.code, exc.message))
        return 1
    finally:
        store.close()


def command_status(args):
    store = SyncStore(args.db)
    try:
        state = store.status()
        emit(event("state", "passed", "STATE_READ", "Local agent state loaded.", {
            "db": os.path.abspath(args.db),
            "accounts": str(len(state["accounts"])),
            "generations": str(len(state["generations"])),
        }))
        return 0
    finally:
        store.close()


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--addr", default="127.0.0.1:5030")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--chatlog-bin", default=DEFAULT_CHATLOG_BIN)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health").set_defaults(func=command_health)
    sub.add_parser("discover").set_defaults(func=command_discover)
    sub.add_parser("accounts").set_defaults(func=command_accounts)
    connect = sub.add_parser("connect")
    connect.add_argument("--account-id", default="")
    connect.set_defaults(func=command_connect)
    switch = sub.add_parser("switch")
    switch.add_argument("--account-id", required=True)
    switch.set_defaults(func=command_switch)
    sync = sub.add_parser("sync")
    sync.add_argument("--account-id", default="")
    sync.add_argument("--limit", type=int, default=5000)
    sync.set_defaults(func=command_sync)
    sub.add_parser("status").set_defaults(func=command_status)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
