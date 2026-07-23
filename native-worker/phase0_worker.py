#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import subprocess
import sys

WECHAT_PATH = "/Applications/WeChat.app/Contents/MacOS/WeChat"
WECHAT_DYLIB_PATH = "/Applications/WeChat.app/Contents/Resources/wechat.dylib"
EXPECTED_BUILD = "269111"
EXPECTED_FULL_DYLIB_SHA256 = "c2a4794b343625a8013752095e76bc688acd42d48f30001a255620db2fc542a9"
EXPECTED_ARM64_SLICE_SHA256 = "da53625065d283d748f959627f5e4d724eb786f2911f49c91a72cc12f17d30f7"


def emit(step, status, code, message, evidence=None):
    print(json.dumps({
        "step": step,
        "status": status,
        "code": code,
        "message": message,
        "evidence": evidence or {},
    }, ensure_ascii=False, sort_keys=True))


def cmd_version(_args):
    try:
        import frida
    except Exception as exc:
        emit("worker_version", "failed", "FRIDA_IMPORT_FAILED", str(exc))
        return 1
    emit("worker_version", "passed", "FRIDA_IMPORT_OK", "Frida import succeeded.", {
        "frida_version": frida.__version__,
        "python": sys.version.split()[0],
    })
    return 0


def find_wechat_pid():
    result = subprocess.run(
        ["/bin/ps", "-axo", "pid,command"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.endswith(WECHAT_PATH):
            return int(stripped.split(None, 1)[0])
    return None


def cmd_probe_process(_args):
    pid = find_wechat_pid()
    if pid is None:
        emit("wechat_process", "blocked", "WECHAT_NOT_RUNNING", "WeChat main process is not running.")
        return 0
    emit("wechat_process", "passed", "WECHAT_PROCESS_FOUND", "WeChat main process is running.", {
        "pid": str(pid),
        "path": WECHAT_PATH,
    })
    return 0


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def plist_value(key):
    result = subprocess.run(
        ["/usr/libexec/PlistBuddy", "-c", "Print:%s" % key, "/Applications/WeChat.app/Contents/Info.plist"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def arm64_slice_sha256():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "wechat.arm64.dylib")
        result = subprocess.run(
            ["/usr/bin/lipo", WECHAT_DYLIB_PATH, "-thin", "arm64", "-output", out_path],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "lipo failed")
        return sha256_file(out_path)


def cmd_profile_gate(_args):
    pid = find_wechat_pid()
    if pid is None:
        emit("wechat_profile", "blocked", "WECHAT_NOT_RUNNING", "WeChat main process is not running.")
        return 0
    if not os.path.exists(WECHAT_DYLIB_PATH):
        emit("wechat_profile", "failed", "WECHAT_DYLIB_MISSING", "wechat.dylib was not found.", {
            "path": WECHAT_DYLIB_PATH,
        })
        return 1

    build = plist_value("CFBundleVersion")
    full_hash = sha256_file(WECHAT_DYLIB_PATH)
    slice_hash = arm64_slice_sha256()
    evidence = {
        "pid": str(pid),
        "build": build,
        "full_dylib_sha256": full_hash,
        "arm64_slice_sha256": slice_hash,
        "dylib_path": WECHAT_DYLIB_PATH,
    }
    mismatches = []
    if build != EXPECTED_BUILD:
        mismatches.append("build")
    if full_hash != EXPECTED_FULL_DYLIB_SHA256:
        mismatches.append("full_dylib_sha256")
    if slice_hash != EXPECTED_ARM64_SLICE_SHA256:
        mismatches.append("arm64_slice_sha256")

    if mismatches:
        evidence["mismatches"] = ",".join(mismatches)
        emit("wechat_profile", "failed", "WECHAT_PROFILE_MISMATCH", "Running WeChat disk profile does not match the certified profile.", evidence)
        return 1

    emit("wechat_profile", "passed", "WECHAT_DISK_PROFILE_MATCH", "WeChat disk profile matches the certified build and dylib hashes.", evidence)
    return 0


def cmd_attach_smoke(_args):
    pid = find_wechat_pid()
    if pid is None:
        emit("attach_smoke", "blocked", "WECHAT_NOT_RUNNING", "WeChat main process is not running.")
        return 0
    try:
        import frida
        session = frida.attach(pid)
        script_path = os.path.join(os.path.dirname(__file__), "probes", "attach_smoke.js")
        with open(script_path, "r", encoding="utf-8") as handle:
            script = session.create_script(handle.read())
        script.load()
        exports = getattr(script, "exports_sync", script.exports)
        result = exports.ping()
        script.unload()
        session.detach()
        emit("attach_smoke", "passed", "ATTACH_SMOKE_PASSED", "Worker attached, loaded probe, unloaded, and detached.", {
            "pid": str(pid),
            "probe": str(result.get("probe", "")) if isinstance(result, dict) else str(result),
        })
        return 0
    except Exception as exc:
        emit("attach_smoke", "failed", "ATTACH_SMOKE_FAILED", str(exc), {"pid": str(pid)})
        return 1


def cmd_cleanup_smoke(_args):
    emit("cleanup_smoke", "passed", "CLEANUP_SMOKE_NOOP", "No persistent helper is owned by this command.")
    return 0


def cmd_text_send_smoke_manifest(_args):
    emit("text_send_smoke", "blocked", "TEXT_SEND_SMOKE_MANUAL_REQUIRED", "Text send smoke is exact-profile gated and must be run explicitly against filehelper.", {
        "target": "filehelper",
        "requires": "exact_profile_logged_in_wechat_visible_ack_cleanup",
    })
    return 0


def main():
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("version").set_defaults(func=cmd_version)
    subcommands.add_parser("probe-process").set_defaults(func=cmd_probe_process)
    subcommands.add_parser("profile-gate").set_defaults(func=cmd_profile_gate)
    subcommands.add_parser("attach-smoke").set_defaults(func=cmd_attach_smoke)
    subcommands.add_parser("cleanup-smoke").set_defaults(func=cmd_cleanup_smoke)
    subcommands.add_parser("text-send-smoke-manifest").set_defaults(func=cmd_text_send_smoke_manifest)
    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
