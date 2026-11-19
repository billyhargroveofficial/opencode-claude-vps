#!/usr/bin/env python3
"""Two separate OpenCode processes, two real DeepSeek turns, one local worktree."""
import json
import secrets
import subprocess
import sys
from pathlib import Path

launcher = Path(__file__).resolve().with_name("opencode-vps")
work = Path(sys.argv[1]).resolve()
work.mkdir(parents=True, exist_ok=False)
subprocess.run(["git", "init", "-q", str(work)], check=True)
marker = "mac-only-" + secrets.token_hex(8)
memory = "chat-only-" + secrets.token_hex(8)
proof = work / "local-proof.txt"
proof.write_text(f"{marker}\nstatus: pending\n")

def turn(prompt, name, session=None):
    args = [str(launcher), "run", "--auto", "--format", "json"]
    if session:
        args += ["--session", session]
    result = subprocess.run([*args, prompt], cwd=work, capture_output=True, text=True, timeout=240)
    events = [json.loads(l) for l in result.stdout.splitlines() if l.startswith("{")]
    if result.returncode or not events or any(x.get("type") == "error" for x in events):
        raise RuntimeError(f"{name} failed: {result.stderr[-1200:]} {events[-1:]}")
    ids = {e["sessionID"] for e in events}
    if len(ids) != 1 or session and ids != {session}:
        raise RuntimeError(f"{name}: unexpected OpenCode session IDs: {ids}")
    tools = [e["part"] for e in events if e["type"] == "tool_use"]
    completed = [t for t in tools if t.get("state", {}).get("status") == "completed"]
    text = "\n".join(e["part"]["text"] for e in events if e["type"] == "text")
    data = {"session": ids.pop(), "tools": [t["tool"] for t in completed], "response": text}
    print(name, json.dumps(data, ensure_ascii=False), flush=True)
    return data, completed

first, tools = turn(
    'Use OpenCode tools to read local-proof.txt, edit only "status: pending" to "status: first", '
    'then run uname -s and pwd with the shell tool. Report the first line, OS, and directory. '
    f'Remember {memory} in this chat only. Never write that value to a file.', "first")
assert proof.read_text() == f"{marker}\nstatus: first\n"
assert "read" in first["tools"] and "edit" in first["tools"]
assert any(t["tool"] == "shell" and "Darwin" in t["state"]["output"] and str(work) in t["state"]["output"] for t in tools)
# --standalone exits with its private server. This command starts a new client and server.
second, _ = turn(
    'Repeat the chat-only string from my previous turn. Use the edit tool to change '
    '"status: first" to "status: second" in local-proof.txt. Read the file back and report both lines.',
    "restart", first["session"])
assert memory in second["response"] and marker in second["response"]
assert "edit" in second["tools"] and "read" in second["tools"]
assert proof.read_text() == f"{marker}\nstatus: second\n"
print("PASS", first["session"], str(proof))
