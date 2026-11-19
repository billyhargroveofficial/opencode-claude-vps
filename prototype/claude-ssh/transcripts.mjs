import { deleteSession, forkSession, getSessionInfo, getSessionMessages } from "@anthropic-ai/claude-agent-sdk"

const [op, id, messageId] = process.argv.slice(2)
if (op === "exists") console.log(JSON.stringify(!!(await getSessionInfo(id))))
else if (op === "delete") {
  await deleteSession(id)
  console.log("true")
} else if (op === "fork") {
  const source = await getSessionMessages(id)
  const boundary = source.findIndex((message) => message.uuid === messageId)
  if (boundary < 0) console.log("null")
  else {
    const fork = await forkSession(id, { upToMessageId: messageId })
    try {
      const copied = await getSessionMessages(fork.sessionId)
      if (copied.length !== boundary + 1) throw Error("fork length mismatch")
      const messages = copied.map((item, index) => {
        const before = source[index]
        if (before.type !== item.type || JSON.stringify(before.message) !== JSON.stringify(item.message))
          throw Error("fork checkpoint mismatch")
        return [before.uuid, item.uuid]
      })
      console.log(JSON.stringify({ sessionID: fork.sessionId, messages }))
    } catch (error) {
      await deleteSession(fork.sessionId)
      throw error
    }
  }
} else throw Error("unknown transcript operation")
