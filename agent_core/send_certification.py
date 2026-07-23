import sqlite3
from typing import Dict, Iterable, List


CERTIFIED_PROFILE = {
    "wechat_version": "4.1.11.55",
    "wechat_build": "269111",
    "dylib_sha256": "c2a4794b343625a8013752095e76bc688acd42d48f30001a255620db2fc542a9",
    "arm64_sha256": "da53625065d283d748f959627f5e4d724eb786f2911f49c91a72cc12f17d30f7",
}

SEND_TYPES = ("text", "image", "video", "file")

CERTIFICATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS send_adapter_certifications (
    adapter_type TEXT NOT NULL,
    wechat_version TEXT NOT NULL,
    wechat_build TEXT NOT NULL,
    dylib_sha256 TEXT NOT NULL,
    arm64_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    certified_at INTEGER NOT NULL,
    PRIMARY KEY(adapter_type, wechat_version, wechat_build, dylib_sha256, arm64_sha256)
);
"""


def ensure_certification_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(CERTIFICATION_SCHEMA)


def certified_capabilities(connection: sqlite3.Connection) -> Dict[str, Dict]:
    ensure_certification_schema(connection)
    rows = connection.execute(
        """SELECT adapter_type,status,evidence_json,certified_at
           FROM send_adapter_certifications
           WHERE wechat_version=? AND wechat_build=? AND dylib_sha256=? AND arm64_sha256=?""",
        (
            CERTIFIED_PROFILE["wechat_version"],
            CERTIFIED_PROFILE["wechat_build"],
            CERTIFIED_PROFILE["dylib_sha256"],
            CERTIFIED_PROFILE["arm64_sha256"],
        ),
    ).fetchall()
    by_type = {row["adapter_type"]: row for row in rows}
    result = {}
    for adapter_type in SEND_TYPES:
        row = by_type.get(adapter_type)
        certified = row is not None and row["status"] == "certified"
        result[adapter_type] = {
            "certified": certified,
            "reason": "CERTIFIED" if certified else "CERTIFICATION_MISSING",
            "certified_at": row["certified_at"] if row is not None else None,
        }
    return result


def required_send_types(batch: Dict) -> List[str]:
    required = {"text"}
    for attachment in batch.get("attachments", []):
        media_type = attachment.get("media_type") if isinstance(attachment, dict) else ""
        if media_type in {"image", "video"}:
            required.add(media_type)
        elif media_type:
            required.add("file")
    return [item for item in SEND_TYPES if item in required]


def uncertified_required_types(connection: sqlite3.Connection, batch: Dict) -> List[str]:
    capabilities = certified_capabilities(connection)
    return [item for item in required_send_types(batch) if not capabilities[item]["certified"]]
