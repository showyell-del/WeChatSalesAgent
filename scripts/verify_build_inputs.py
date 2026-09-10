#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if "__pycache__" in path.parts or path.name == ".DS_Store" or path.suffix == ".pyc":
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        if path.is_symlink():
            digest.update(b"L\0" + relative + b"\0" + os.readlink(path).encode("utf-8") + b"\0")
        elif path.is_file():
            digest.update(b"F\0" + relative + b"\0" + sha256(path).encode("ascii") + b"\0")
    return digest.hexdigest()


def stdlib_tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    excluded = {"site-packages", "__pycache__", "test", "tests"}
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative_path = path.relative_to(root)
        if excluded.intersection(relative_path.parts) or path.name == ".DS_Store" or path.suffix == ".pyc":
            continue
        relative = relative_path.as_posix().encode("utf-8")
        if path.is_symlink():
            digest.update(b"L\0" + relative + b"\0" + os.readlink(path).encode("utf-8") + b"\0")
        elif path.is_file():
            digest.update(b"F\0" + relative + b"\0" + sha256(path).encode("ascii") + b"\0")
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--node-root", type=Path, required=True)
    parser.add_argument("--python-packages", type=Path, required=True)
    parser.add_argument("--frida-source", type=Path, required=True)
    parser.add_argument("--python-source", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    node = args.node_root / "bin/node"
    artifact_root = args.node_root / "node_modules/@oai/artifact-tool"
    artifact_package = artifact_root / "package.json"
    required = [node, artifact_package, args.python_packages / "pydantic", args.python_packages / "pydantic_core",
                args.python_packages / "annotated_types", args.python_packages / "typing_inspection",
                args.python_packages / "typing_extensions.py", args.frida_source / "_frida.abi3.so",
                args.python_source / "bin/python3.9", args.python_source / "Python3",
                args.python_source / "Resources", args.python_source / "lib/python3.9"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("BUILD_INPUT_MISSING: " + ", ".join(missing))
    checks = {
        "node_version": subprocess.check_output([str(node), "--version"], text=True).strip(),
        "node_sha256": sha256(node),
        "artifact_version": json.loads(artifact_package.read_text(encoding="utf-8"))["version"],
        "artifact_tree_sha256": tree_sha256(artifact_root),
        "python_runtime_version": subprocess.check_output(
            [str(args.python_source / "bin/python3.9"), "-c", "import sys; print(sys.version.split()[0])"], text=True,
        ).strip(),
        "python_runtime_arch": "arm64" if "arm64" in subprocess.check_output(
            ["/usr/bin/file", str(args.python_source / "bin/python3.9")], text=True,
        ) else "unsupported",
        "python_executable_sha256": sha256(args.python_source / "bin/python3.9"),
        "python_library_sha256": sha256(args.python_source / "Python3"),
        "python_resources_tree_sha256": tree_sha256(args.python_source / "Resources"),
        "python_stdlib_tree_sha256": stdlib_tree_sha256(args.python_source / "lib/python3.9"),
    }
    script = "import frida,pydantic,pydantic_core,json,pathlib; print(json.dumps([pydantic.VERSION,pydantic_core.__version__,frida.__version__,str(pathlib.Path(pydantic.__file__).resolve().parent),str(pathlib.Path(pydantic_core.__file__).resolve().parent),str(pathlib.Path(frida.__file__).resolve().parent)]))"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(args.python_packages)
    environment["PYTHONNOUSERSITE"] = "1"
    imported = json.loads(subprocess.check_output([sys.executable, "-S", "-c", script], text=True, env=environment))
    expected_paths = [(args.python_packages / "pydantic").resolve(), (args.python_packages / "pydantic_core").resolve(), args.frida_source.resolve()]
    if [Path(value) for value in imported[3:]] != expected_paths:
        raise RuntimeError("BUILD_INPUT_IMPORT_PATH_MISMATCH: " + json.dumps({"expected": [str(value) for value in expected_paths], "actual": imported[3:]}, sort_keys=True))
    checks.update({
        "pydantic_version": imported[0], "pydantic_tree_sha256": tree_sha256(args.python_packages / "pydantic"),
        "pydantic_core_version": imported[1], "pydantic_core_tree_sha256": tree_sha256(args.python_packages / "pydantic_core"),
        "frida_version": imported[2], "frida_tree_sha256": tree_sha256(args.frida_source),
        "annotated_types_tree_sha256": tree_sha256(args.python_packages / "annotated_types"),
        "typing_inspection_tree_sha256": tree_sha256(args.python_packages / "typing_inspection"),
        "typing_extensions_sha256": sha256(args.python_packages / "typing_extensions.py"),
    })
    expected = {
        "node_version": manifest["node"]["version"],
        "node_sha256": manifest["node"]["sha256"],
        "artifact_version": manifest["artifact_tool"]["version"],
        "artifact_tree_sha256": manifest["artifact_tool"]["tree_sha256"],
        **manifest["python_runtime"],
        **manifest["python_packages"],
    }
    if checks != expected:
        raise RuntimeError("BUILD_INPUT_MISMATCH: " + json.dumps({"expected": expected, "actual": checks}, sort_keys=True))
    print(json.dumps(checks, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
