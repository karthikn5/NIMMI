/**
 * When Nimmi (the dashboard's agent) changes something, the open page shows it at once: the panel announces the
 * change, and every useApi on the page loads its data again; pages with their own loading (the builder) listen too.
 */
export const AGENT_CHANGED = "nimmi:changed";

/** What changed: an assistant, a voice agent or script, a question, Schedule, the team. */
export type AgentChange = { kind: string; id: string; deleted?: boolean };

export function announceChange(change: AgentChange) {
    if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent<AgentChange>(AGENT_CHANGED, { detail: change }));
}
