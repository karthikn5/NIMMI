/** The agent's server-sent events (AG-UI names: RUN_STARTED, TEXT_MESSAGE_CONTENT, TOOL_CALL_START...). */
export type AgentEvent = { type: string; seq: number } & Record<string, unknown>;

/** Reads an event stream to its end, calling onEvent for each event. Throws if the connection drops. */
export async function readEvents(res: Response, onEvent: (e: AgentEvent) => void): Promise<void> {
    if (!res.body) throw new Error("No response body");
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let end: number;
        while ((end = buffer.indexOf("\n\n")) >= 0) {
            const block = buffer.slice(0, end);
            buffer = buffer.slice(end + 2);
            for (const line of block.split("\n")) {
                if (!line.startsWith("data: ")) continue; // ": ping" keeps the connection open
                try {
                    onEvent(JSON.parse(line.slice(6)) as AgentEvent);
                } catch { /* a broken line: skip it */ }
            }
        }
    }
}
