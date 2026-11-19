#!/usr/bin/env python3
"""Build the macOS arm64 CLI without pulling down a native Claude executable."""
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
if platform.system() != "Darwin" or platform.machine() != "arm64":
    raise SystemExit("This prototype targets Apple Silicon.")
bun = shutil.which("bun")
required = json.loads((repo / "package.json").read_text())["packageManager"].removeprefix("bun@")
if not bun or subprocess.check_output([bun, "--version"], text=True).strip() != required:
    raise SystemExit(f"Put Bun {required} on PATH first.")
subprocess.run([bun, "install", "--frozen-lockfile", "--omit", "optional"], cwd=repo, check=True)
# Restore just the native packages used by the build and repository checks.
packages = [
    "@opencode/pty-darwin-arm64", "@opentui/core-darwin-arm64", "@parcel/watcher-darwin-arm64",
    "@ff-labs/fff-bin-darwin-arm64", "@yuuang/ffi-rs-darwin-arm64",
    "@img/sharp-darwin-arm64", "@img/sharp-libvips-darwin-arm64", "@ast-grep/cli-darwin-arm64",
    "@oxlint/binding-darwin-arm64", "@turbo/darwin-arm64", "@typescript/typescript-darwin-arm64",
    "@esbuild/darwin-arm64", "@oxc-parser/binding-darwin-arm64",
]
lock = (repo / "bun.lock").read_text()
pins = {}
for name in packages:
    match = re.search(r'^    "' + re.escape(name) + r'": \["' + re.escape(name) + r'@([^"]+)"', lock, re.M)
    if not match:
        raise SystemExit(f"No lockfile entry for {name}")
    pins[name] = match[1]
scratch = Path.home() / "harness-temp"
scratch.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=scratch, prefix="oc-build-") as tmp:
    stage = Path(tmp)
    (stage / "package.json").write_text(json.dumps({"private": True, "dependencies": pins}))
    subprocess.run([bun, "install", "--ignore-scripts"], cwd=stage, check=True)
    for name, version in pins.items():
        dst = repo / "node_modules" / name
        if dst.exists() and json.loads((dst / "package.json").read_text())["version"] == version:
            continue
        if dst.exists():
            raise SystemExit(f"Unexpected installed version in {dst}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage / "node_modules" / name, dst)
env = {**os.environ, "OPENCODE_CHANNEL": "prototype", "OPENCODE_VERSION": "2.3.2"}
subprocess.run([bun, "run", "--cwd", "packages/cli", "script/build.ts", "--single", "--skip-install", "--skip-web-ui"],
               cwd=repo, env=env, check=True)
