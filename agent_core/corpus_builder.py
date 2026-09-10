import sqlite3
from typing import Dict, List, Tuple

from .chatlog_client import ChatlogClient, ChatlogError
from .corpus_store import CorpusStore, evidence_id
from .extractors import extract_facts


SYSTEM_USERNAMES = {
    "brandsessionholder",
    "brandservicesessionholder",
    "notification_messages",
    "notificationholder",
    "newsapp",
    "filehelper",
    "fmessage",
    "medianote",
    "floatbottle",
    "qmessage",
    "weixin",
    "weibo",
    "qqmail",
}
SYSTEM_SENDERS = {"系统消息", "系统通知"}
TEXT_TYPES = {"text", "link", "quote"}


def static_exclusion(session: Dict) -> str:
    username = str(session.get("username", ""))
    display = str(session.get("chat", ""))
    if (
        session.get("is_group")
        or username.endswith("@chatroom")
        or session.get("chat_type") == "group"
    ):
        return "GROUP_CHAT"
    if username.startswith("gh_"):
        return "OFFICIAL_ACCOUNT"
    if username in SYSTEM_USERNAMES or username.startswith("brandservice"):
        return "SYSTEM_SESSION"
    if any(term in display for term in ("公众号", "服务通知", "微信支付", "腾讯新闻")):
        return "SERVICE_SESSION"
    return ""


def meaningful_messages(messages: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    inbound = []
    outbound = []
    for message in messages:
        content = str(message.get("content", "")).strip()
        sender = str(message.get("sender", "")).strip()
        if not content or sender in SYSTEM_SENDERS or message.get("type") == "system":
            continue
        target = outbound if message.get("is_self") else inbound
        target.append(message)
    return inbound, outbound


def has_effective_interaction(inbound: List[Dict], outbound: List[Dict]) -> bool:
    inbound_text = [
        item
        for item in inbound
        if item.get("type") in TEXT_TYPES and str(item.get("content", "")).strip()
    ]
    outbound_text = [
        item
        for item in outbound
        if item.get("type") in TEXT_TYPES and str(item.get("content", "")).strip()
    ]
    return bool(inbound_text and outbound_text)


def build_corpus(
    db_path: str,
    account_id: str,
    since_ts: int,
    until_ts: int,
    addr: str = "127.0.0.1:5030",
    page_size: int = 500,
) -> Dict:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    store = CorpusStore(connection)
    client = ChatlogClient(addr)
    corpus_id = ""
    try:
        generation = store.published_generation(account_id)
        sessions = store.sessions(generation["generation_id"])
        corpus_id = store.create_run(
            generation["generation_id"], account_id, since_ts, until_ts
        )
        for session in sessions:
            exclusion = static_exclusion(session)
            if exclusion:
                store.add_conversation(
                    corpus_id,
                    session,
                    "excluded",
                    exclusion,
                    0,
                    0,
                    int(session.get("timestamp") or 0),
                )
                store.commit_conversation()
                continue
            messages = client.history(
                session["username"], since_ts, until_ts, page_size
            )
            inbound, outbound = meaningful_messages(messages)
            if not has_effective_interaction(inbound, outbound):
                store.add_conversation(
                    corpus_id,
                    session,
                    "excluded",
                    "NO_BIDIRECTIONAL_TEXT",
                    len(inbound),
                    len(outbound),
                    max([int(item.get("timestamp") or 0) for item in messages] or [0]),
                )
                store.commit_conversation()
                continue
            latest = max(int(item.get("timestamp") or 0) for item in messages)
            store.add_conversation(
                corpus_id, session, "eligible", "", len(inbound), len(outbound), latest
            )
            for message in messages:
                content = str(message.get("content", "")).strip()
                if (
                    not content
                    or message.get("type") not in TEXT_TYPES
                    or str(message.get("sender", "")) in SYSTEM_SENDERS
                ):
                    continue
                item_id = evidence_id(
                    account_id,
                    generation["generation_id"],
                    session["username"],
                    message,
                )
                facts = (
                    extract_facts(content, item_id)
                    if not message.get("is_self")
                    else []
                )
                store.add_evidence_and_facts(
                    corpus_id,
                    account_id,
                    generation["generation_id"],
                    session["username"],
                    message,
                    facts,
                )
            store.commit_conversation()
        store.publish_run(corpus_id, account_id)
        counts = store.run_counts(corpus_id)
        counts.update(
            {
                "corpus_id": corpus_id,
                "generation_id": generation["generation_id"],
                "account_id": account_id,
            }
        )
        return counts
    except ChatlogError as exc:
        if corpus_id:
            store.fail_run(corpus_id, exc.code, exc.message)
        raise
    except Exception as exc:
        if corpus_id:
            store.fail_run(corpus_id, "CORPUS_BUILD_FAILED", str(exc))
        raise
    finally:
        connection.close()
