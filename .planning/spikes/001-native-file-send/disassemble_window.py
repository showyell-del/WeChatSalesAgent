#!/usr/bin/env python3
"""Dump a small runtime instruction window from the loaded WeChat dylib."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import frida

ROOT = Path(__file__).resolve().parent
AGENT = ROOT / "disassemble_window_agent.js"
APP = Path("/Applications/WeChat.app")


def find_pid() -> int:
    command = str(APP / "Contents/MacOS/WeChat")
    output = subprocess.check_output(["ps", "-axo", "pid=,command="], text=True)
    pids = [int(line.strip().split(maxsplit=1)[0]) for line in output.splitlines() if line.strip().endswith(command)]
    if len(pids) != 1:
        raise RuntimeError(f"expected one WeChat process, got {pids}")
    return pids[0]


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: disassemble_window.py <hex-offset> <count>", file=sys.stderr)
        return 2
    start = int(argv[1], 16)
    count = int(argv[2], 10)
    session = frida.get_local_device().attach(find_pid())
    script = session.create_script(AGENT.read_text(encoding="utf-8"))
    try:
        script.load()
        rows = script.exports_sync.dump(start, count)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    finally:
        try:
            script.unload()
        finally:
            session.detach()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
