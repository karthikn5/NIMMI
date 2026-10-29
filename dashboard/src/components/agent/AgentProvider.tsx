"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { activeOwnerId, apiFetch, apiJson, currentUserId } from "@/lib/api";
import { readEvents, type AgentEvent } from "@/lib/agent/stream";
import { announceChange, type AgentChange } from "@/lib/agent/changes";
import { screenFor, type Screen } from "@/lib/agent/screens";
import AgentPanel from "./AgentPanel";
import type { Card } from "./AgentCards";

/**
 * Nimmi, the dashboard's own agent: the panel beside every dashboard screen (backend/agent; NIMMI_AGENT_PLAN.md).
 * This keeps the chat, sends what's on screen with each message, streams the answer, and carries on after a dropped
 * connection or a reload (the run keeps going on the server; its saved events are replayed from the last one seen).
 * It also does what the agent asks of the screen: open a page, point at something.
 */

export type Item =
    | { type: "user"; id: string; text: string }
    | { type: "text"; id: string; text: string }
    | { type: "step"; id: string; label: string; ok?: boolean; running?: boolean; actionId?: string; undoable?: boolean; undone?: boolean; busy?: boolean }
    | { type: "confirm"; id: string; actionId: string; title: string; summary: string; state: string; message?: string; busy?: boolean }
    | { type: "note"; id: string; text: string }
    | { type: "card"; id: string; card: Card; active: boolean; busy?: boolean }
    | { type: "error"; id: string; text: string };
export type ThreadSummary = { id: string; title: string; updated_at: string };
type PageInfo = Partial<Pick<Screen, "tab" | "entity" | "details" | "errors">>;
type PageHooks = { flush?: () => Promise<unknown> | void };

type AgentState = {
    open: boolean;
    toggle: () => void;
    close: () => void;
    docked: boolean;
    canDock: boolean;
    setDocked: (v: boolean) => void;
    width: number;
    setWidth: (w: number) => void;
    ready: boolean | null;
    items: Item[];
    running: boolean;
    threadId: string | null;
    send: (text: string) => void;
    stop: () => void;
    newChat: () => void;
    threads: ThreadSummary[] | null;
    loadThreads: () => void;
    openThread: (id: string) => void;
    deleteThread: (id: string) => void;
    screen: () => Screen;
    setPage: (info: PageInfo | null, hooks?: PageHooks) => void;
    decide: (actionId: string, choice: "confirm" | "cancel") => void;
    undo: (actionId: string) => void;
    jobStep: (jobId: string, step: string, payload: Record<string, unknown>) => void;
};

const AgentContext = createContext<AgentState | null>(null);
export const useAgent = () => useContext(AgentContext);

/**
 * A page says more about itself than its route does: the open tab, the assistant it shows, errors on screen.
 * `flush` saves the page's unsaved edits; the panel runs it before each message, so Nimmi works on what's saved.
 */
export function useAgentScreen(info: PageInfo, hooks?: PageHooks) {
    const agent = useContext(AgentContext);
    const setPage = agent?.setPage;
    const key = JSON.stringify(info);
    const latest = useRef(hooks);
    latest.current = hooks;
    useEffect(() => {
        if (!setPage) return;
        setPage(JSON.parse(key) as PageInfo, { flush: () => latest.current?.flush?.() });
        return () => setPage(null);
    }, [key, setPage]);
}

const WIDTH = { min: 360, max: 520, start: 400 };

function stored(key: string): string | null {
    try { return localStorage.getItem(key); } catch { return null; }
}
function store(key: string, value: string | null) {
    try {
        if (value === null) localStorage.removeItem(key);
        else localStorage.setItem(key, value);
    } catch { /* storage blocked: fine, it just isn't remembered */ }
}
const threadKey = () => `nimmi_agent_thread:${currentUserId()}:${activeOwnerId()}`;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const DONE = new Set(["RUN_FINISHED", "RUN_ERROR"]);

/** Highlight an element the pages named with data-agent, waiting a little for it (a page that just opened). */
async function pointAt(name: string): Promise<boolean> {
    for (let i = 0; i < 15; i++) {
        const el = Array.from(document.querySelectorAll<HTMLElement>(`[data-agent="${CSS.escape(name)}"]`))
            .find((e) => e.getClientRects().length > 0);
        if (el) {
            el.scrollIntoView({ block: "center", behavior: "smooth" });
            const before = { outline: el.style.outline, offset: el.style.outlineOffset };
            el.style.outline = "2px solid #550a64";
            el.style.outlineOffset = "3px";
            el.animate?.([{ boxShadow: "0 0 0 0 rgba(85,10,100,0.35)" }, { boxShadow: "0 0 0 12px rgba(85,10,100,0)" }],
                         { duration: 1000, iterations: 3 });
            setTimeout(() => { el.style.outline = before.outline; el.style.outlineOffset = before.offset; }, 3200);
            return true;
        }
        await sleep(200);
    }
    return false;
}

export default function AgentProvider({ children }: { children: ReactNode }) {
    const router = useRouter();
    const [open, setOpen] = useState(false);
    const [docked, setDockedState] = useState(true);
    const [canDock, setCanDock] = useState(false);
    const [width, setWidthState] = useState(WIDTH.start);
    const [ready, setReady] = useState<boolean | null>(null);
    const [items, setItems] = useState<Item[]>([]);
    const [running, setRunning] = useState(false);
    const [threadId, setThreadId] = useState<string | null>(null);
    const [threads, setThreads] = useState<ThreadSummary[] | null>(null);
    const page = useRef<{ path: string; info: PageInfo; hooks?: PageHooks } | null>(null);
    const runId = useRef<string | null>(null);
    const lastSeq = useRef(0);
    const generation = useRef(0); // a stream from an older chat stops updating the screen
    const restored = useRef(false);
    const lastEnd = useRef<"done" | "error">("done");

    // Remembered per person: open or closed, docked or floating, how wide.
    useEffect(() => {
        setOpen(stored("nimmi_agent_open") === "1");
        setDockedState(stored("nimmi_agent_docked") !== "0");
        const w = Number(stored("nimmi_agent_width"));
        if (w >= WIDTH.min && w <= WIDTH.max) setWidthState(w);
        const wide = window.matchMedia("(min-width: 1280px)");
        const update = () => setCanDock(wide.matches);
        update();
        wide.addEventListener("change", update);
        return () => wide.removeEventListener("change", update);
    }, []);

    const screen = useCallback((): Screen => {
        const base = screenFor(window.location.pathname, window.location.search);
        const info = page.current?.path === window.location.pathname ? page.current.info : null;
        if (!info) return base;
        const details = { ...(base.details ?? {}), ...(info.details ?? {}) };
        return { ...base, ...info, entity: info.entity ?? base.entity, ...(Object.keys(details).length ? { details } : {}) };
    }, []);

    const setPage = useCallback((info: PageInfo | null, hooks?: PageHooks) => {
        page.current = info ? { path: window.location.pathname, info, hooks } : null;
    }, []);

    /** Something changed: the open page shows it; an assistant that was deleted closes its own pages. */
    const changed = useCallback((change: AgentChange) => {
        announceChange(change);
        if (change.deleted && change.id && window.location.pathname.includes(change.id)) router.push("/dashboard");
    }, [router]);

    const addError = useCallback((text: string) => {
        setItems((all) => [...all, { type: "error", id: `e-${Date.now()}`, text }]);
    }, []);

    /** Apply one event; true when the run has ended. */
    const apply = useCallback((e: AgentEvent): boolean => {
        lastSeq.current = Math.max(lastSeq.current, e.seq || 0);
        switch (e.type) {
            case "RUN_STARTED":
                runId.current = String(e.runId);
                setThreadId(String(e.threadId));
                store(threadKey(), String(e.threadId));
                break;
            case "TEXT_MESSAGE_START":
                setItems((all) => all.some((i) => i.id === e.messageId) ? all : [...all, { type: "text", id: String(e.messageId), text: "" }]);
                break;
            case "TEXT_MESSAGE_CONTENT":
                setItems((all) => all.map((i) => i.id === e.messageId && i.type === "text" ? { ...i, text: i.text + String(e.delta) } : i));
                break;
            case "TOOL_CALL_START":
                setItems((all) => all.some((i) => i.id === e.toolCallId) ? all
                    : [...all, { type: "step", id: String(e.toolCallId), label: String(e.label || e.toolCallName), running: true }]);
                break;
            case "TOOL_CALL_RESULT":
                setItems((all) => all.map((i) => i.id === e.toolCallId && i.type === "step"
                    ? { ...i, running: false, ok: !!e.ok, ...(e.actionId ? { actionId: String(e.actionId), undoable: !!e.undoable } : {}) } : i));
                break;
            case "CUSTOM": {
                const value = (e.value ?? {}) as Record<string, string>;
                if (e.name === "navigate" && typeof value.path === "string" && value.path.startsWith("/dashboard")) router.push(value.path);
                if (e.name === "highlight" && value.element) void pointAt(value.element);
                if (e.name === "changed") changed(value as unknown as AgentChange);
                if (e.name === "card" && value.jobId) {
                    const card = value as unknown as Card;
                    setItems((all) => [...all, { type: "card", id: `card-${card.jobId}-${card.kind}`, card, active: card.kind !== "result" }]);
                }
                if (e.name === "confirm" && value.actionId) {
                    setItems((all) => all.some((i) => i.id === `confirm-${value.actionId}`) ? all : [...all, {
                        type: "confirm", id: `confirm-${value.actionId}`, actionId: value.actionId, title: value.title,
                        summary: value.summary, state: "proposed",
                    }]);
                }
                break;
            }
            case "STEP_STARTED":
                setItems((all) => [...all, { type: "step", id: `step-${runId.current}-${e.stepName}`, label: String(e.label || e.stepName), running: true }]);
                break;
            case "STEP_FINISHED":
                setItems((all) => all.map((i) => i.id === `step-${runId.current}-${e.stepName}` && i.type === "step"
                    ? { ...i, running: false, ok: !!e.ok, label: e.detail ? `${i.label}: ${e.detail}` : i.label } : i));
                break;
            case "RUN_ERROR":
                lastEnd.current = "error";
                addError(String(e.message || "Something went wrong."));
                return true;
            case "RUN_FINISHED":
                lastEnd.current = "done";
                return true;
        }
        return false;
    }, [addError, changed, router]);

    /** Read a run's events until it ends, reconnecting from the last one seen when the connection drops. */
    const follow = useCallback(async (first: Promise<Response>, gen: number) => {
        setRunning(true);
        let res: Response | null = await first.catch(() => null);
        if (res && !res.ok) {
            const body = await res.json().catch(() => ({}));
            if (gen === generation.current) {
                addError(typeof body.detail === "string" ? body.detail : `That didn't work (${res.status}).`);
                setRunning(false);
            }
            return;
        }
        for (let tries = 0; gen === generation.current;) {
            let ended = false;
            if (res) {
                try {
                    await readEvents(res, (e) => {
                        if (gen !== generation.current) return;
                        tries = 0;
                        if (apply(e)) ended = true;
                    });
                } catch { /* the connection dropped: pick up below */ }
            }
            if (ended || gen !== generation.current) break;
            if (!runId.current || ++tries > 6) {
                addError("Lost the connection to Nimmi. Open this chat again in a moment to see the answer.");
                break;
            }
            await sleep(Math.min(500 * 2 ** tries, 8000));
            res = await apiFetch(`/api/agent/runs/${runId.current}/events?after=${lastSeq.current}`).catch(() => null);
            if (res && !res.ok) res = null;
        }
        if (gen === generation.current) {
            setRunning(false);
            runId.current = null;
        }
    }, [addError, apply]);

    const load = useCallback(async (id: string) => {
        const gen = ++generation.current;
        try {
            const thread = await apiJson<{ id: string; items: Item[]; running: { id: string } | null }>(`/api/agent/threads/${id}`);
            if (gen !== generation.current) return;
            setThreadId(thread.id);
            setItems(thread.items);
            store(threadKey(), thread.id);
            if (thread.running) {
                runId.current = thread.running.id;
                lastSeq.current = 0;
                void follow(apiFetch(`/api/agent/runs/${thread.running.id}/events?after=0`), gen);
            }
        } catch {
            if (gen !== generation.current) return;
            store(threadKey(), null); // gone, or from another workspace
            setThreadId(null);
            setItems([]);
        }
    }, [follow]);

    // When the panel opens: is Nimmi set up here, and the last chat back.
    useEffect(() => {
        if (!open || !currentUserId()) return;
        if (ready === null) {
            apiJson<{ ready: boolean }>("/api/agent/status").then((s) => setReady(s.ready)).catch(() => setReady(false));
        }
        if (!restored.current) {
            restored.current = true;
            const last = stored(threadKey());
            if (last) void load(last);
        }
    }, [open, ready, load]);

    const send = useCallback((text: string) => {
        const clean = text.trim();
        if (!clean || running) return;
        const gen = ++generation.current;
        runId.current = null;
        lastSeq.current = 0;
        setItems((all) => [...all, { type: "user", id: `u-${Date.now()}`, text: clean }]);
        setRunning(true);
        // The page's unsaved edits first (up to 5 s), so a change Nimmi makes isn't saved over by them afterwards.
        const flushed = Promise.race([Promise.resolve(page.current?.hooks?.flush?.()).catch(() => {}), sleep(5000)]);
        const start = flushed.then(() => apiFetch("/api/agent/messages", { method: "POST", json: { text: clean, thread_id: threadId, screen: screen() } }));
        void follow(start, gen);
    }, [follow, running, screen, threadId]);

    /** A card's step: the builder works on the server and its events come like an answer's; a step that failed can be
     * tried again from the same card. */
    const jobStep = useCallback((jobId: string, step: string, payload: Record<string, unknown>) => {
        if (running) return;
        const gen = ++generation.current;
        runId.current = null;
        lastSeq.current = 0;
        lastEnd.current = "done";
        const setCard = (patch: Partial<Extract<Item, { type: "card" }>>) => setItems((all) => all.map((i) =>
            i.type === "card" && i.card.jobId === jobId && i.card.kind === step ? { ...i, ...patch } : i));
        setCard({ busy: true, active: false });
        void follow(apiFetch(`/api/agent/jobs/${jobId}/${step}`, { method: "POST", json: payload }), gen).then(() => {
            setCard(lastEnd.current === "error" ? { busy: false, active: true } : { busy: false });
        });
    }, [follow, running]);

    const note = useCallback((text: string) => {
        setItems((all) => [...all, { type: "note", id: `n-${Date.now()}`, text }]);
    }, []);

    const decide = useCallback((actionId: string, choice: "confirm" | "cancel") => {
        const set = (patch: Partial<Extract<Item, { type: "confirm" }>>) => setItems((all) => all.map((i) =>
            i.type === "confirm" && i.actionId === actionId ? { ...i, ...patch } : i));
        set({ busy: true });
        apiJson<{ state: string; message?: string; summary: string; refresh?: AgentChange[] }>(
            `/api/agent/actions/${actionId}/${choice}`, { method: "POST" })
            .then((r) => {
                set({ busy: false, state: r.state, message: r.message });
                r.refresh?.forEach(changed);
                note(r.state === "done" ? `Done: ${r.message ?? r.summary}` : r.state === "cancelled" ? "Cancelled. Nothing was changed." : r.message ?? r.state);
            })
            .catch((err: Error) => { set({ busy: false }); addError(err.message); });
    }, [addError, changed, note]);

    const undo = useCallback((actionId: string) => {
        const set = (patch: Partial<Extract<Item, { type: "step" }>>) => setItems((all) => all.map((i) =>
            i.type === "step" && i.actionId === actionId ? { ...i, ...patch } : i));
        set({ busy: true });
        apiJson<{ state: string; summary: string; refresh?: AgentChange[] }>(`/api/agent/actions/${actionId}/undo`, { method: "POST" })
            .then((r) => {
                set({ busy: false, undoable: false, undone: true });
                r.refresh?.forEach(changed);
                note(`Undone: ${r.summary}`);
            })
            .catch((err: Error) => { set({ busy: false }); addError(err.message); });
    }, [addError, changed, note]);

    const stop = useCallback(() => {
        if (runId.current) void apiFetch(`/api/agent/runs/${runId.current}/stop`, { method: "POST" }).catch(() => {});
    }, []);

    const newChat = useCallback(() => {
        generation.current++;
        runId.current = null;
        setRunning(false);
        setItems([]);
        setThreadId(null);
        store(threadKey(), null);
    }, []);

    const loadThreads = useCallback(() => {
        apiJson<ThreadSummary[]>("/api/agent/threads").then(setThreads).catch(() => setThreads([]));
    }, []);

    const deleteThread = useCallback((id: string) => {
        apiFetch(`/api/agent/threads/${id}`, { method: "DELETE" }).then((res) => {
            if (!res.ok) return;
            setThreads((all) => (all ?? []).filter((t) => t.id !== id));
            if (id === threadId) newChat();
        }).catch(() => {});
    }, [newChat, threadId]);

    const toggle = useCallback(() => setOpen((o) => { store("nimmi_agent_open", o ? "0" : "1"); return !o; }), []);
    const close = useCallback(() => { store("nimmi_agent_open", "0"); setOpen(false); }, []);
    const setDocked = useCallback((v: boolean) => { store("nimmi_agent_docked", v ? "1" : "0"); setDockedState(v); }, []);
    const setWidth = useCallback((w: number) => {
        const clamped = Math.round(Math.min(WIDTH.max, Math.max(WIDTH.min, w)));
        store("nimmi_agent_width", String(clamped));
        setWidthState(clamped);
    }, []);

    // Ctrl + / opens and closes the panel anywhere in the dashboard (the Control key on a Mac too).
    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (e.ctrlKey && !e.metaKey && !e.altKey && e.key === "/") {
                e.preventDefault();
                toggle();
            }
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [toggle]);

    const value = useMemo<AgentState>(() => ({
        open, toggle, close, docked, canDock, setDocked, width, setWidth, ready, items, running, threadId, send, stop,
        newChat, threads, loadThreads, openThread: (id: string) => void load(id), deleteThread, screen, setPage, decide, undo, jobStep,
    }), [open, toggle, close, docked, canDock, setDocked, width, setWidth, ready, items, running, threadId, send, stop,
         newChat, threads, loadThreads, load, deleteThread, screen, setPage, decide, undo, jobStep]);

    const dockedNow = open && docked && canDock;
    // The same elements in every mode, so the page itself is never re-created when the panel moves.
    return (
        <AgentContext.Provider value={value}>
            <div className={dockedNow ? "grid" : undefined} style={dockedNow ? { gridTemplateColumns: `minmax(0, 1fr) ${width}px` } : undefined}>
                <div className="min-w-0">{children}</div>
                {open && <AgentPanel docked={dockedNow} />}
            </div>
        </AgentContext.Provider>
    );
}
