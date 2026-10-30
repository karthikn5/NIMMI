"use client";

import { useEffect, useSyncExternalStore } from "react";
import { apiFetch, apiJson, getToken } from "@/lib/api";
import { liveSocket } from "@/lib/liveChat";

/**
 * Live calls for the whole dashboard (LIVE_CALLS_PLAN.md): the calls going on now, and callers waiting for a person.
 * One shared copy per page, read every few seconds (that also tells the server this person is here, so callers can
 * be offered to them) and at once when the server announces a change over the socket. The server runs several
 * processes: the socket reaches only dashboards on the same one, so the regular check is what makes it reliable.
 */
export type LiveLine = { speaker: "caller" | "agent"; text: string };
export type LiveCall = {
    id: string; caller: string; caller_name: string | null; test: boolean; bot_name: string; direction: "inbound" | "outbound";
    started_at: string | null; seconds: number; state: "assistant" | "waiting" | "connecting" | "person";
    person: string | null; handoff_id: string | null; lines: LiveLine[];
};
export type CallRequest = {
    id: string; call_id: string | null; caller: string; caller_name: string | null; test: boolean; bot_name: string;
    reason: string; status: string; waited_sec: number; left_sec: number; browser: boolean; phone: boolean;
    lines: LiveLine[]; mine: boolean;
};
export type LiveState = {
    calls: LiveCall[]; requests: CallRequest[]; me: { available: boolean; phone: string };
    loaded: boolean; at: number; // when it was read (for the timers between reads)
};

const EVERY_MS = 3000;
let state: LiveState = { calls: [], requests: [], me: { available: true, phone: "" }, loaded: false, at: 0 };
const listeners = new Set<() => void>();
let users = 0;
let timer: ReturnType<typeof setInterval> | null = null;
let inFlight = false;

function publish(next: Partial<LiveState>) {
    state = { ...state, ...next };
    listeners.forEach((l) => l());
}

export async function refreshLive() {
    if (inFlight || !getToken()) return;
    inFlight = true;
    try {
        const data = await apiJson<Omit<LiveState, "loaded" | "at">>("/api/voice/live");
        publish({ ...data, loaded: true, at: Date.now() });
    } catch { /* offline for a moment: the next check tries again */ } finally {
        inFlight = false;
    }
}

function start() {
    users += 1;
    if (users > 1) return;
    void refreshLive();
    timer = setInterval(() => void refreshLive(), EVERY_MS);
    liveSocket()?.on("call_handoff", refreshLive);
}

function stop() {
    users -= 1;
    if (users > 0) return;
    if (timer) clearInterval(timer);
    timer = null;
    liveSocket()?.off("call_handoff", refreshLive);
}

/** The live calls and waiting callers, kept current while a component uses them. */
export function useLive(): LiveState {
    useEffect(() => { start(); return stop; }, []);
    return useSyncExternalStore((cb) => { listeners.add(cb); return () => listeners.delete(cb); }, () => state, () => state);
}

async function post(path: string, body?: unknown): Promise<{ ok: boolean; message: string; data?: Record<string, unknown> }> {
    try {
        const res = await apiFetch(path, { method: "POST", ...(body === undefined ? {} : { json: body }) });
        const data = await res.json().catch(() => ({}));
        return { ok: res.ok, message: typeof data.detail === "string" ? data.detail : res.ok ? "" : "That didn't work. Try again.", data };
    } catch {
        return { ok: false, message: "Couldn't reach Nimmi. Check your connection." };
    }
}

export async function acceptCall(id: string, via: "browser" | "phone", phone?: string) {
    const r = await post(`/api/voice/live/handoffs/${id}/accept`, { via, ...(phone ? { phone } : {}) });
    void refreshLive();
    return r;
}

export async function declineCall(id: string) {
    const r = await post(`/api/voice/live/handoffs/${id}/decline`);
    void refreshLive();
    return r;
}

export async function setAvailability(patch: { available?: boolean; phone?: string }) {
    const r = await post("/api/voice/live/presence", patch);
    if (r.ok && r.data) publish({ me: { available: !!r.data.available, phone: String(r.data.phone || "") } });
    return r;
}

export async function browserToken(id: string) {
    return post("/api/voice/live/token", { handoff_id: id });
}

export const formatClock = (sec: number) => `${Math.floor(sec / 60)}:${String(Math.max(0, sec) % 60).padStart(2, "0")}`;
