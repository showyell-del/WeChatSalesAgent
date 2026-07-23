#!/usr/bin/env python3
"""Passively observe real WeChat Req2Buf tree nodes without sending messages."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import frida

ROOT = Path(__file__).resolve().parent
AGENT = ROOT / "node_observer_agent.js"
EVENTS = ROOT / "node-observer-events.jsonl"
APP = Path("/Applications/WeChat.app")
DYLIB = APP / "Contents/Resources/wechat.dylib"
EXPECTED_DYLIB_SHA256 = "c2a4794b343625a8013752095e76bc688acd42d48f30001a255620db2fc542a9"
EXPECTED_ARM64_SHA256 = "da53625065d283d748f959627f5e4d724eb786f2911f49c91a72cc12f17d30f7"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record(category: str, event: str, **fields: object) -> None:
    item = {"timestamp": utc_now(), "category": category, "event": event, **fields}
    with EVENTS.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps(item, ensure_ascii=False, sort_keys=True), flush=True)


def exact_profile_gate() -> tuple[str, str]:
    full_hash = sha256(DYLIB)
    if full_hash != EXPECTED_DYLIB_SHA256:
        raise RuntimeError(f"wechat.dylib hash mismatch: {full_hash}")
    with tempfile.TemporaryDirectory(prefix="wechat-node-observer-") as directory:
        thin = Path(directory) / "wechat-arm64.dylib"
        subprocess.run(["lipo", str(DYLIB), "-thin", "arm64", "-output", str(thin)], check=True)
        arm_hash = sha256(thin)
    if arm_hash != EXPECTED_ARM64_SHA256:
        raise RuntimeError(f"wechat.dylib arm64 hash mismatch: {arm_hash}")
    return full_hash, arm_hash


def find_pid() -> int:
    command = str(APP / "Contents/MacOS/WeChat")
    output = subprocess.check_output(["ps", "-axo", "pid=,command="], text=True)
    pids = [int(line.strip().split(maxsplit=1)[0]) for line in output.splitlines() if line.strip().endswith(command)]
    if len(pids) != 1:
        raise RuntimeError(f"expected one WeChat process, got {pids}")
    return pids[0]


def main() -> int:
    EVENTS.unlink(missing_ok=True)
    full_hash, arm_hash = exact_profile_gate()
    pid = find_pid()
    seconds = int(os.getenv("CHATLOG_NODE_OBSERVER_SECONDS", "45"))
    record("lifecycle", "start", pid=pid, seconds=seconds, frida=frida.__version__,
           full_hash=full_hash, arm64_hash=arm_hash)
    session = None
    script = None
    try:
        session = frida.get_local_device().attach(pid)
        script = session.create_script(AGENT.read_text(encoding="utf-8"))

        def on_message(message: dict[str, object], data: bytes | None) -> None:
            if message.get("type") != "send":
                record("frida", "error", message=message, data_bytes=len(data or b""))
                return
            item = dict(message.get("payload") or {})
            category = str(item.pop("category", "native_node_observer"))
            event_name = str(item.pop("event", "message"))
            record(category, event_name, **item)

        script.on("message", on_message)
        script.load()
        record("lifecycle", "script_loaded")
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            time.sleep(0.5)
        status = script.exports_sync.status()
        record("lifecycle", "finished_wait", status=status)
        return 0
    except Exception as exc:
        record("result", "failed", error=repr(exc))
        return 1
    finally:
        if script is not None:
            try:
                script.exports_sync.stop()
            except Exception as exc:
                record("cleanup", "stop_failed", error=repr(exc))
            try:
                script.unload()
                record("cleanup", "script_unloaded")
            except Exception as exc:
                record("cleanup", "unload_failed", error=repr(exc))
        if session is not None:
            try:
                session.detach()
                record("cleanup", "session_detached")
            except Exception as exc:
                record("cleanup", "detach_failed", error=repr(exc))


if __name__ == "__main__":
    sys.exit(main())
