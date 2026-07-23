#!/usr/bin/env python3
"""Send one deterministic file to filehelper through WeChat's native protocol."""

from __future__ import annotations

import hashlib
import html
import json
import os
import random
import string
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import frida

ROOT = Path(__file__).resolve().parent
AGENT = ROOT / "file_send_agent.js"
EVENTS = ROOT / "file-send-events.jsonl"
RESULT = ROOT / "file-send-result.json"
APP = Path("/Applications/WeChat.app")
DYLIB = APP / "Contents/Resources/wechat.dylib"
EXPECTED_DYLIB_SHA256 = "c2a4794b343625a8013752095e76bc688acd42d48f30001a255620db2fc542a9"
EXPECTED_ARM64_SHA256 = "da53625065d283d748f959627f5e4d724eb786f2911f49c91a72cc12f17d30f7"
SENDER = "wxid_3prysbeqgvci22"
RECEIVER = "filehelper"
CHUNK_SIZE = 50_000


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
    with tempfile.TemporaryDirectory(prefix="wechat-file-spike-") as directory:
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


def varint(value: int) -> bytes:
    if value < 0:
        value &= (1 << 64) - 1
    output = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        output.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(output)


def field_varint(number: int, value: int) -> bytes:
    return varint(number << 3) + varint(value)


def field_bytes(number: int, value: bytes | str) -> bytes:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return varint((number << 3) | 2) + varint(len(data)) + data


def decode_fields(data: bytes) -> list[tuple[int, int, object]]:
    result: list[tuple[int, int, object]] = []
    index = 0

    def read_varint() -> int:
        nonlocal index
        value = 0
        shift = 0
        while index < len(data):
            byte = data[index]
            index += 1
            value |= (byte & 0x7F) << shift
            if byte < 0x80:
                return value
            shift += 7
            if shift > 70:
                raise ValueError("invalid varint")
        raise ValueError("truncated varint")

    while index < len(data):
        tag = read_varint()
        number, wire = tag >> 3, tag & 7
        if wire == 0:
            value: object = read_varint()
        elif wire == 2:
            length = read_varint()
            if index + length > len(data):
                raise ValueError("truncated bytes field")
            value = data[index:index + length]
            index += length
        elif wire == 1:
            value = data[index:index + 8]
            index += 8
        elif wire == 5:
            value = data[index:index + 4]
            index += 4
        else:
            raise ValueError(f"unsupported wire type {wire}")
        result.append((number, wire, value))
    return result


class ProtocolState:
    def __init__(self) -> None:
        self.session_id = random.randrange(100_000_000, 4_100_000_000)
        self.device_id = random.getrandbits(32) | (0xFFFFFFFF << 32)
        suffix = "".join(random.choice(string.digits + string.ascii_lowercase) for _ in range(13))
        self.client_proof = f"m64{suffix}".encode("ascii")
        self.task_id = 0x21000000

    def next_task(self) -> int:
        self.task_id += 1
        return self.task_id

    def header(self, version: int) -> bytes:
        return b"".join([
            field_bytes(1, b"\x00"),
            field_varint(2, self.session_id),
            field_bytes(3, self.client_proof),
            field_varint(4, self.device_id),
            field_bytes(5, "UnifiedPCMac 26 arm64"),
            field_varint(6, version),
        ])


def build_upload_chunk(state: ProtocolState, receiver: str, client_id: str, file_md5: str,
                       total: int, start: int, chunk: bytes, version: int) -> bytes:
    data_buffer = field_varint(1, len(chunk)) + field_bytes(2, chunk)
    return b"".join([
        field_bytes(1, state.header(version)),
        field_bytes(2, b""),
        field_varint(3, 0),
        field_bytes(4, client_id),
        field_bytes(5, receiver),
        field_varint(6, total),
        field_varint(7, start),
        field_varint(8, len(chunk)),
        field_bytes(9, data_buffer),
        field_varint(10, 6),
        field_bytes(11, file_md5),
    ])


def parse_upload_response(data: bytes) -> str:
    fields = decode_fields(data)
    base_values = [value for number, wire, value in fields if number == 1 and wire == 2]
    if len(base_values) != 1:
        raise RuntimeError("upload response missing BaseResponse")
    base_fields = decode_fields(base_values[0])
    ret_values = [value for number, wire, value in base_fields if number == 1 and wire == 0]
    if len(ret_values) != 1 or ret_values[0] != 0:
        raise RuntimeError(f"upload response ret={ret_values}")
    media_values = [value for number, wire, value in fields if number == 3 and wire == 2]
    if not media_values:
        return ""
    return media_values[-1].decode("utf-8")


def build_file_message(state: ProtocolState, sender: str, receiver: str, name: str, extension: str,
                       total: int, attach_id: str, version: int) -> bytes:
    now = int(time.time())
    xml = (
        "<?xml version=\"1.0\"?>\n<appmsg appid='' sdkver=''>"
        f"<title>{html.escape(name)}</title><des></des><action></action><type>6</type>"
        "<content></content><url></url><lowurl></lowurl><appattach>"
        f"<totallen>{total}</totallen><attachid>{html.escape(attach_id)}</attachid>"
        f"<fileext>{html.escape(extension)}</fileext></appattach><extinfo></extinfo></appmsg>"
    )
    body = b"".join([
        field_bytes(1, sender),
        field_bytes(2, b""),
        field_varint(3, 0),
        field_bytes(4, receiver),
        field_varint(5, 6),
        field_bytes(6, xml),
        field_varint(7, now),
        field_bytes(8, str(now)),
        field_bytes(12, "<msgsource><alnode><fr>1</fr><cf>2</cf></alnode></msgsource>"),
    ])
    return field_bytes(1, state.header(version)) + field_bytes(2, body)


def parse_base_response(data: bytes) -> int:
    top = decode_fields(data)
    base_values = [value for number, wire, value in top if number == 1 and wire == 2]
    if len(base_values) != 1:
        raise RuntimeError("send response missing BaseResponse")
    base = decode_fields(base_values[0])
    values = [value for number, wire, value in base if number == 1 and wire == 0]
    if len(values) != 1:
        raise RuntimeError("send response missing ret")
    return int(values[0])


def build_payload(task_id: int, message_type: str) -> bytes:
    data = bytearray(412)
    seed = bytes([
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x40, 0xEC, 0x0E, 0x12,
        0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x30, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x80, 0x00, 0x01, 0x01, 0x01, 0x00, 0xAA, 0xAA, 0xAA,
        0x00, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,
        0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0xAA, 0xAA, 0xAA,
        0xFF, 0xFF, 0xFF, 0xFF, 0xAA, 0xAA, 0xAA, 0xAA, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x64, 0x65, 0x66, 0x61, 0x75, 0x6C, 0x74, 0x2D, 0x6C, 0x6F, 0x6E, 0x67,
        0x6C, 0x69, 0x6E, 0x6B, 0x00, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0x10,
    ])
    data[:len(seed)] = seed
    data[0] = 0x6E
    data[16] = 0x10
    data[0] = 0x0A if message_type == "text" else 0x6E
    data[1] = 0x02 if message_type == "text" else data[1]
    data[16] = 0x01 if message_type == "text" else 0x10
    data[28] = 0x25 if message_type == "appattach" else 0x20
    data[92] = 0x0A if message_type == "text" else 0x6E
    data[93] = 0x02 if message_type == "text" else data[93]
    payload = bytearray(0x1A0)
    payload[:4] = task_id.to_bytes(4, "little")
    payload[4:] = data
    return bytes(payload)


def wait_event(condition: threading.Condition, events: list[dict[str, object]], start: int,
               predicate, timeout: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    with condition:
        while True:
            for item in events[start:]:
                if predicate(item):
                    return item
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("timed out waiting for native event")
            condition.wait(min(remaining, 0.5))


def call_with_timeout(name: str, func, timeout: float = 3.0) -> None:
    result: dict[str, object] = {}

    def runner() -> None:
        try:
            func()
            result["ok"] = True
        except Exception as exc:  # pragma: no cover - diagnostic runner
            result["error"] = exc

    thread = threading.Thread(target=runner, name=name, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError(f"{name} timed out")
    if "error" in result:
        raise result["error"]  # type: ignore[misc]


def main() -> int:
    EVENTS.unlink(missing_ok=True)
    RESULT.unlink(missing_ok=True)
    full_hash, arm_hash = exact_profile_gate()
    marker = f"native-file-spike-{int(time.time())}"
    test_file = ROOT / f"{marker}.txt"
    content = (marker + "\n" + "WeChat native file-send verification\n").encode("utf-8")
    test_file.write_bytes(content)
    source_sha = sha256(test_file)
    pid = find_pid()
    record("lifecycle", "start", pid=pid, frida=frida.__version__, full_hash=full_hash, arm64_hash=arm_hash,
           test_file=str(test_file), source_sha256=source_sha, source_bytes=len(content))

    condition = threading.Condition()
    events: list[dict[str, object]] = []
    session = None
    script = None
    script_loaded = False
    cleanup = {"forced": False, "script_unloaded": False, "session_detached": False}
    state = ProtocolState()
    try:
        session = frida.get_local_device().attach(pid)
        script = session.create_script(AGENT.read_text(encoding="utf-8"))

        def on_message(message: dict[str, object], data: bytes | None) -> None:
            if message.get("type") != "send":
                record("frida", "error", message=message, data_bytes=len(data or b""))
                return
            item = dict(message.get("payload") or {})
            category = str(item.pop("category", "native_file"))
            event_name = str(item.pop("event", "message"))
            record(category, event_name, **item)
            with condition:
                events.append({"event": event_name, **item})
                condition.notify_all()

        script.on("message", on_message)
        script.load()
        script_loaded = True
        profile = script.exports_sync.profile()
        record("native_file", "hook_profile", **profile)
        record("lifecycle", "script_loaded")
        status = script.exports_sync.status()
        if not status.get("dispatch_ready"):
            raise RuntimeError(f"native dispatch unavailable: {status}")
        record("lifecycle", "dispatch_ready", status=status)

        if os.getenv("CHATLOG_SPIKE_TEXT") == "1":
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and not script.exports_sync.status().get("context_ready"):
                time.sleep(0.2)
            if not script.exports_sync.status().get("context_ready"):
                raise RuntimeError("real StartTask manager context was not observed; ensure WeChat is logged into the normal chat workspace")
            task = state.next_task()
            marker = f"native-text-cert-{int(time.time())}"
            body = b"".join([
                field_bytes(1, field_bytes(1, RECEIVER)),
                field_bytes(2, marker),
                field_varint(3, 1),
                field_varint(4, int(time.time())),
                field_varint(5, random.randrange(1 << 34, 1 << 35)),
                field_bytes(6, "<msgsource><alnode><fr>1</fr></alnode></msgsource>"),
            ])
            text_proto = field_varint(1, 1) + field_bytes(2, body)
            event_start = len(events)
            triggered = script.exports_sync.trigger(task, "text", text_proto.hex(), build_payload(task, "text").hex())
            if not triggered.get("ok"):
                raise RuntimeError(f"text trigger failed: {triggered}")
            response_event = wait_event(condition, events, event_start,
                                        lambda item: item.get("event") == "buf2resp" and item.get("task_id") == task, 20)
            ret = parse_base_response(bytes.fromhex(str(response_event["data_hex"])))
            if ret != 0:
                raise RuntimeError(f"newsendmsg returned ret={ret}")
            record("result", "native_text_protocol_ack", task_id=task, receiver=RECEIVER, marker=marker, ret=ret)
            time.sleep(5)
            return 0

        if os.getenv("CHATLOG_SPIKE_DIRECT_FILE") == "1":
            task = state.next_task()
            file_proto = build_file_message(state, SENDER, RECEIVER, test_file.name, "txt", len(content), "@fake_attach_id", task)
            event_start = len(events)
            triggered = script.exports_sync.trigger(task, "file", file_proto.hex(), build_payload(task, "file").hex())
            if not triggered.get("ok"):
                raise RuntimeError(f"direct file trigger failed: {triggered}")
            response_event = wait_event(condition, events, event_start,
                                        lambda item: item.get("event") == "buf2resp" and item.get("task_id") == task, 20)
            ret = parse_base_response(bytes.fromhex(str(response_event["data_hex"])))
            record("result", "direct_file_response", task_id=task, ret=ret)
            return 0

        file_md5 = hashlib.md5(content).hexdigest()
        client_id = f"{RECEIVER}_{int(time.time())}_UploadFile"
        attach_id = ""
        for start in range(0, len(content), CHUNK_SIZE):
            chunk = content[start:start + CHUNK_SIZE]
            task = state.next_task()
            proto = build_upload_chunk(state, RECEIVER, client_id, file_md5, len(content), start, chunk, task)
            event_start = len(events)
            triggered = script.exports_sync.trigger(task, "appattach", proto.hex(), build_payload(task, "appattach").hex())
            if not triggered.get("ok"):
                raise RuntimeError(f"upload trigger failed: {triggered}")
            response_event = wait_event(condition, events, event_start,
                                        lambda item: item.get("event") == "buf2resp" and item.get("task_id") == task, 20)
            current_id = parse_upload_response(bytes.fromhex(str(response_event["data_hex"])))
            if current_id:
                attach_id = current_id
            record("protocol", "chunk_accepted", task_id=task, start=start, bytes=len(chunk), attach_id=attach_id)
        if not attach_id:
            raise RuntimeError("uploadappattach returned no attach_id")

        task = state.next_task()
        file_proto = build_file_message(state, SENDER, RECEIVER, test_file.name, "txt", len(content), attach_id, task)
        event_start = len(events)
        triggered = script.exports_sync.trigger(task, "file", file_proto.hex(), build_payload(task, "file").hex())
        if not triggered.get("ok"):
            raise RuntimeError(f"file trigger failed: {triggered}")
        response_event = wait_event(condition, events, event_start,
                                    lambda item: item.get("event") == "buf2resp" and item.get("task_id") == task, 20)
        ret = parse_base_response(bytes.fromhex(str(response_event["data_hex"])))
        if ret != 0:
            raise RuntimeError(f"sendappmsg returned ret={ret}")
        result = {
            "verdict": "NATIVE_PROTOCOL_ACK",
            "receiver": RECEIVER,
            "sender": SENDER,
            "task_id": task,
            "attach_id": attach_id,
            "file_name": test_file.name,
            "source_path": str(test_file),
            "source_bytes": len(content),
            "source_sha256": source_sha,
            "sendappmsg_ret": ret,
        }
        RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        record("result", "native_protocol_ack", **result)
        time.sleep(5)
        return 0
    except Exception as exc:
        record("result", "failed", error=repr(exc))
        return 1
    finally:
        if script is not None and script_loaded:
            try:
                call_with_timeout("script.unload", script.unload)
                cleanup["script_unloaded"] = True
            except Exception as exc:
                record("cleanup", "unload_failed", error=repr(exc))
        if session is not None:
            try:
                call_with_timeout("session.detach", session.detach)
                cleanup["session_detached"] = True
            except Exception as exc:
                record("cleanup", "detach_failed", error=repr(exc))
        record("cleanup", "complete", **cleanup)


if __name__ == "__main__":
    sys.exit(main())
