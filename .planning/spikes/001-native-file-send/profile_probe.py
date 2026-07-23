#!/usr/bin/env python3
"""Read-only WeChat 4.1.11.55 hook-profile discovery with deterministic cleanup."""

from __future__ import annotations

import hashlib
import json
import plistlib
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import frida

ROOT = Path(__file__).resolve().parent
AGENT = ROOT / "profile_probe.js"
EVENTS = ROOT / "events.jsonl"
PROFILE = ROOT / "profile-4.1.11.55.json"
APP = Path("/Applications/WeChat.app")
INFO = APP / "Contents/Info.plist"
DYLIB = APP / "Contents/Resources/wechat.dylib"
EXPECTED_BUNDLE_VERSION = "4.1.11.55"
EXPECTED_BUILD = "269111"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def event(category: str, name: str, **fields: object) -> None:
    record = {"timestamp": now(), "category": category, "event": name, **fields}
    with EVENTS.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps(record, ensure_ascii=False, sort_keys=True), flush=True)


def find_pid() -> int:
    output = subprocess.check_output(["ps", "-axo", "pid=,command="], text=True)
    command = str(APP / "Contents/MacOS/WeChat")
    matches = [int(line.strip().split(maxsplit=1)[0]) for line in output.splitlines() if line.strip().endswith(command)]
    if len(matches) != 1:
        raise RuntimeError(f"expected one WeChat main process, got {matches}")
    return matches[0]


def app_metadata() -> dict[str, str]:
    with INFO.open("rb") as stream:
        info = plistlib.load(stream)
    bundle_version = str(info.get("WeChatBundleVersion", ""))
    build = str(info.get("CFBundleVersion", ""))
    if bundle_version != EXPECTED_BUNDLE_VERSION or build != EXPECTED_BUILD:
        raise RuntimeError(
            f"profile target mismatch: bundle={bundle_version!r} build={build!r}; "
            f"expected {EXPECTED_BUNDLE_VERSION!r}/{EXPECTED_BUILD!r}"
        )
    return {"bundle_version": bundle_version, "build": build}


def main() -> int:
    started = time.monotonic()
    EVENTS.unlink(missing_ok=True)
    metadata = app_metadata()
    full_hash = sha256(DYLIB)
    pid = find_pid()
    event("lifecycle", "start", pid=pid, frida=frida.__version__, dylib_sha256=full_hash, **metadata)

    session = None
    script = None
    cleanup = {"script_unloaded": False, "session_detached": False}
    try:
        device = frida.get_local_device()
        session = device.attach(pid)
        event("lifecycle", "attached", pid=pid)
        script = session.create_script(AGENT.read_text(encoding="utf-8"))

        def on_message(message: dict[str, object], data: bytes | None) -> None:
            if message.get("type") == "send":
                payload = dict(message.get("payload") or {})
                category = str(payload.pop("category", "frida"))
                event_name = str(payload.pop("event", "message"))
                if "name" in payload:
                    payload["probe_name"] = payload.pop("name")
                event(category, event_name, **payload)
            else:
                event("frida", "error", message=message, data_bytes=len(data or b""))

        script.on("message", on_message)
        script.load()
        event("lifecycle", "script_loaded")
        report = script.exports_sync.inspect()
        offsets: dict[str, str] = {}
        ambiguous: dict[str, int] = {}
        for probe in report["probes"]:
            matches = probe["matches"]
            if len(matches) == 1:
                offsets[probe["name"]] = matches[0]["candidate_offset"]
            else:
                ambiguous[probe["name"]] = len(matches)
        profile = {
            "wechat_bundle_version": metadata["bundle_version"],
            "wechat_build": metadata["build"],
            "dylib_sha256": full_hash,
            "frida_version": frida.__version__,
            "offsets": offsets,
            "ambiguous": ambiguous,
            "source": "read-only pattern scan; candidates require instruction and live observation validation"
        }
        PROFILE.write_text(json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        event("result", "profile_written", path=str(PROFILE), offsets=len(offsets), ambiguous=ambiguous)
        if ambiguous:
            return 2
        return 0
    except Exception as exc:
        event("result", "failed", error=repr(exc))
        return 1
    finally:
        if script is not None:
            try:
                script.unload()
                cleanup["script_unloaded"] = True
            except Exception as exc:
                event("cleanup", "script_unload_failed", error=repr(exc))
        if session is not None:
            try:
                session.detach()
                cleanup["session_detached"] = True
            except Exception as exc:
                event("cleanup", "session_detach_failed", error=repr(exc))
        event("cleanup", "complete", duration_ms=round((time.monotonic() - started) * 1000), **cleanup)


if __name__ == "__main__":
    sys.exit(main())
