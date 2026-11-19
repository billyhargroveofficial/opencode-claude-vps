#!/usr/bin/python3
"""Restricted SSH entry point. stdout is reserved for the SDK protocol."""
import json
import os
from pathlib import Path
import re
import sys
import uuid

HOME = Path("/var/lib/oc-claude-proto")
os.umask(0o077)

def serve():
    if os.environ.get("SSH_ORIGINAL_COMMAND") != "opencode-claude":
        raise ValueError("expected the opencode-claude protocol")
    # An unbuffered descriptor leaves any following SDK packet for the child process.
    header = os.fdopen(os.dup(0), "rb", buffering=0)
    with header:
        line = header.readline(2 * 1024 * 1024)
    if not line.endswith(b"\n"):
        raise ValueError("incomplete bridge request")
    request = json.loads(line)
    env = {"HOME": str(HOME), "USER": "oc-claude-proto", "PATH": "/usr/bin:/bin",
           "LANG": "C.UTF-8", "CLAUDE_CONFIG_DIR": str(HOME / "state")}
    op = request["op"]
    if op in ("exists", "delete", "fork"):
        args = [str(uuid.UUID(request["sessionID"]))]
        if op == "fork":
            args.append(str(uuid.UUID(request["messageID"])))
        os.execve(HOME / "bin/bun", ["bun", str(HOME / "transcripts.mjs"), op, *args], env)
    if op != "run" or not re.fullmatch("[0-9a-f]{64}", request["project"]):
        raise ValueError("invalid launch")
    args = request["args"]
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise ValueError("invalid arguments")
    root = HOME / "work" / request["project"]
    root.mkdir(exist_ok=True)
    env.update({
        "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
        "ANTHROPIC_AUTH_TOKEN": (HOME / "deepseek.key").read_text().strip(),
        "ANTHROPIC_MODEL": "deepseek-flash",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "deepseek-flash",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "deepseek-flash",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "deepseek-flash",
        "CLAUDE_CODE_SUBAGENT_MODEL": "deepseek-flash",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
        "DISABLE_AUTO_COMPACT": "1", "ENABLE_TOOL_SEARCH": "false",
        "CLAUDE_CODE_DISABLE_ADVISOR_TOOL": "1", "MAX_MCP_OUTPUT_TOKENS": "200000",
        "CLAUDE_CODE_POLISHED_DEWDROP": "drop",
    })
    # No prompts, tool payloads, environment values, or API keys in the audit.
    event = {"op": op, "model": "deepseek-flash", "pid": os.getpid(), "project": request["project"]}
    for flag in ("--resume","--session-id","--model"):
        if flag in args:
            event[flag] = args[args.index(flag) + 1]
    with (HOME / "launches.jsonl").open("a") as log:
        log.write(json.dumps(event) + "\n")
    os.chdir(root)
    os.execve(HOME / "bin/claude", ["claude", *args], env)

if __name__ == "__main__":
    try:
        serve()
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        print("Claude SSH bridge:", type(error).__name__, file=sys.stderr)
        sys.exit(2)
