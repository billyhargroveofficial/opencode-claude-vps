import { spawn } from "node:child_process"
import { createHash } from "node:crypto"
import type { ClaudeIO } from "./io.js"
import type { ClaudeFork } from "./fork.js"

// Keep MCP handlers in OpenCode. Only the CLI's stdio and its transcript operations cross SSH.
export function sshIO(target: string): ClaudeIO.Interface {
  const config = process.env.OPENCODE_CLAUDE_SSH_CONFIG
  const configArgs = config ? ["-F", config] : []
  const connect = (signal?: AbortSignal) =>
    spawn(
      "ssh",
      [
        ...configArgs,
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        "--",
        target,
        "opencode-claude",
      ],
      {
        stdio: ["pipe", "pipe", "pipe"],
        signal,
      },
    )

  async function manage<T>(op: string, sessionID: string, messageID?: string): Promise<T> {
    const child = connect(AbortSignal.timeout(30_000))
    const result = new Promise<T>((resolve, reject) => {
      let out = ""
      let err = ""
      child.stdout.setEncoding("utf8").on("data", (data) => {
        out += data
      })
      child.stderr.setEncoding("utf8").on("data", (data) => {
        err = (err + data).slice(-2048)
      })
      child.stdin.on("error", reject)
      child.once("error", reject)
      child.once("close", (code) => {
        if (code !== 0) return reject(new Error(`Claude SSH ${op} failed (${code}): ${err}`))
        try {
          resolve(JSON.parse(out) as T)
        } catch (error) {
          reject(error)
        }
      })
    })
    child.stdin.end(JSON.stringify({ op, sessionID, messageID }) + "\n")
    return result
  }

  return {
    which: () => "/var/lib/oc-claude-proto/bin/claude",
    env: () => ({ ANTHROPIC_BASE_URL: "https://api.deepseek.com/anthropic" }),
    spawn: (options) => {
      const child = connect(options.signal)
      // Do not send the Mac's process environment or its SSH credentials to the VPS.
      const project = createHash("sha256")
        .update(options.cwd ?? process.cwd())
        .digest("hex")
      child.stdin.write(JSON.stringify({ op: "run", args: options.args, project }) + "\n")
      return child
    },
    sessionExists: (sessionID) => manage<boolean>("exists", sessionID),
    remove: async (sessionID) => {
      await manage("delete", sessionID)
    },
    fork: async (sessionID, messageID): Promise<ClaudeFork.Result | undefined> => {
      const fork = await manage<{ sessionID: string; messages: [string, string][] } | null>(
        "fork",
        sessionID,
        messageID,
      )
      if (fork) return { sessionID: fork.sessionID, messages: new Map(fork.messages) }
    },
  }
}
