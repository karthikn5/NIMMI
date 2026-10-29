"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { usePathname } from "next/navigation";
import { ArrowUp, Check, CircleAlert, Eye, History, Loader2, PanelRight, PictureInPicture2, Plus, Square, Trash2, Undo2, X } from "lucide-react";
import { cn } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { announceChange } from "@/lib/agent/changes";
import { suggestionsFor } from "@/lib/agent/screens";
import AgentText from "./AgentText";
import AgentCard from "./AgentCards";
import { useAgent, type Item } from "./AgentProvider";

/** The agent's panel: docked beside the page on wide screens, floating otherwise, a sheet from the bottom on phones. */
export default function AgentPanel({ docked }: { docked: boolean }) {
    const agent = useAgent()!;
    const pathname = usePathname();
    const [draft, setDraft] = useState("");
    const [showHistory, setShowHistory] = useState(false);
    const [showShared, setShowShared] = useState(false);
    const [historyTab, setHistoryTab] = useState<"chats" | "changes">("chats");
    const [screen, setScreen] = useState(() => agent.screen());
    const list = useRef<HTMLDivElement>(null);
    const box = useRef<HTMLTextAreaElement>(null);
    const atBottom = useRef(true);

    // The screen pill follows the page (pages tell their details a moment after they open).
    useEffect(() => {
        setScreen(agent.screen());
        const t = setTimeout(() => setScreen(agent.screen()), 400);
        return () => clearTimeout(t);
    }, [pathname, agent, agent.items.length]);

    // Keep the newest words in view, unless they scrolled up to read.
    useEffect(() => {
        const el = list.current;
        if (el && atBottom.current) el.scrollTop = el.scrollHeight;
    }, [agent.items]);

    useEffect(() => { box.current?.focus(); }, []);

    const submit = () => {
        if (!draft.trim() || agent.running) return;
        agent.send(draft);
        setDraft("");
        atBottom.current = true;
        setShowHistory(false);
    };
    const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
        }
    };
    const onPanelKey = (e: KeyboardEvent<HTMLElement>) => {
        if (e.key === "Escape" && !docked) agent.close();
    };

    const startResize = (e: PointerEvent<HTMLDivElement>) => {
        e.preventDefault();
        const move = (ev: globalThis.PointerEvent) => agent.setWidth(window.innerWidth - ev.clientX);
        const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
    };

    const name = (() => {
        try { return (localStorage.getItem("nimmi_user_name") || "").trim().split(/\s+/)[0]; } catch { return ""; }
    })();
    const empty = agent.items.length === 0;
    const last = agent.items[agent.items.length - 1];
    const thinking = agent.running && (!last || last.type === "user" || (last.type === "step" && !last.running));

    return (
        <aside
            role="complementary"
            aria-label="Nimmi assistant"
            onKeyDown={onPanelKey}
            className={cn(
                "flex flex-col bg-white text-ink",
                docked
                    ? "sticky top-0 h-screen border-l border-line"
                    : "fixed z-40 inset-x-0 bottom-0 h-[85dvh] rounded-t-2xl border border-line shadow-[0_-12px_40px_rgba(28,23,25,0.16)] " +
                      "sm:inset-x-auto sm:right-4 sm:bottom-4 sm:w-[400px] sm:h-[min(640px,calc(100dvh-2rem))] sm:rounded-xl sm:shadow-[0_16px_48px_rgba(28,23,25,0.18)]",
            )}
        >
            {docked && (
                <div onPointerDown={startResize} role="separator" aria-orientation="vertical" aria-label="Resize the panel"
                     className="absolute left-0 top-0 h-full w-1.5 -translate-x-1/2 cursor-col-resize hover:bg-plum/20 z-10" />
            )}

            <header className="h-14 shrink-0 flex items-center gap-2.5 px-3 border-b border-line">
                <img src="/agent/nimmi.svg" alt="" className="h-8 w-8 rounded-full border border-line" />
                <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold leading-tight">Nimmi</p>
                    <p className="text-[11px] text-stone-500 leading-tight truncate">
                        {agent.running ? "Answering…" : agent.ready === false ? "Not set up on this server" : "Your dashboard assistant"}
                    </p>
                </div>
                <IconButton label="Past chats" pressed={showHistory} onClick={() => { setShowHistory((s) => !s); if (!showHistory) agent.loadThreads(); }}>
                    <History size={16} />
                </IconButton>
                <IconButton label="New chat" onClick={() => { agent.newChat(); setShowHistory(false); box.current?.focus(); }}>
                    <Plus size={16} />
                </IconButton>
                {agent.canDock && (
                    <IconButton label={docked ? "Float the panel" : "Dock the panel beside the page"} onClick={() => agent.setDocked(!docked)}>
                        {docked ? <PictureInPicture2 size={16} /> : <PanelRight size={16} />}
                    </IconButton>
                )}
                <IconButton label="Close Nimmi" onClick={agent.close}><X size={16} /></IconButton>
            </header>

            <div className="shrink-0 px-3 py-2 border-b border-line bg-paper">
                <button type="button" onClick={() => setShowShared((s) => !s)} aria-expanded={showShared}
                        className="max-w-full inline-flex items-center gap-1.5 h-6 px-2 rounded-full bg-white border border-line text-[11px] text-stone-600 hover:text-ink">
                    <Eye size={12} aria-hidden />
                    <span className="truncate">Viewing: {screen.title}{screen.tab ? ` · ${screen.tab[0].toUpperCase()}${screen.tab.slice(1)}` : ""}{screen.entity?.name ? ` · ${screen.entity.name}` : ""}</span>
                </button>
                {showShared && (
                    <div className="mt-2 text-[11px] text-stone-600">
                        <p>Sent with your message, so Nimmi knows where you are:</p>
                        <pre className="mt-1 max-h-40 overflow-auto rounded-md bg-white border border-line p-2 font-mono text-[10.5px] leading-snug whitespace-pre-wrap">{JSON.stringify(screen, null, 2)}</pre>
                    </div>
                )}
            </div>

            {showHistory ? (
                <div className="flex-1 overflow-y-auto p-2">
                    <div role="tablist" className="flex gap-1 px-1 pb-2">
                        {(["chats", "changes"] as const).map((t) => (
                            <button key={t} type="button" role="tab" aria-selected={historyTab === t} onClick={() => setHistoryTab(t)}
                                    className={cn("h-7 px-2.5 rounded-md text-[12.5px]", historyTab === t ? "bg-stone-100 font-medium text-ink" : "text-stone-500 hover:text-ink")}>
                                {t === "chats" ? "Past chats" : "Changes"}
                            </button>
                        ))}
                    </div>
                    {historyTab === "changes" ? <Changes /> : agent.threads === null ? (
                        <p className="px-2 py-3 text-[13px] text-stone-500">Loading…</p>
                    ) : agent.threads.length === 0 ? (
                        <p className="px-2 py-3 text-[13px] text-stone-500">No chats yet.</p>
                    ) : agent.threads.map((t) => (
                        <div key={t.id} className={cn("group flex items-center gap-1 rounded-md hover:bg-stone-50", t.id === agent.threadId && "bg-plum-tint")}>
                            <button type="button" onClick={() => { agent.openThread(t.id); setShowHistory(false); }}
                                    className="flex-1 min-w-0 text-left px-2 py-2">
                                <span className="block text-[13px] truncate">{t.title}</span>
                                <span className="block text-[11px] text-stone-500">{new Date(t.updated_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</span>
                            </button>
                            <IconButton label={`Delete "${t.title}"`} onClick={() => agent.deleteThread(t.id)} className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100">
                                <Trash2 size={14} />
                            </IconButton>
                        </div>
                    ))}
                </div>
            ) : (
                <div ref={list} role="log" aria-label="Conversation with Nimmi"
                     onScroll={(e) => { const el = e.currentTarget; atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40; }}
                     className="flex-1 overflow-y-auto px-3 py-4 space-y-3 text-[13.5px] leading-relaxed">
                    {empty ? (
                        <div className="pt-2">
                            <p className="font-medium">{name ? `Hi ${name}, I'm Nimmi.` : "Hi, I'm Nimmi."}</p>
                            <p className="mt-1 text-stone-600">Ask me about this screen, or anything in your dashboard. I can look things up, open pages and show you where to click.</p>
                            {agent.ready === false ? (
                                <p className="mt-3 text-[13px] text-signal">Nimmi isn&apos;t set up on this server yet: it needs an AI service key.</p>
                            ) : (
                                <div className="mt-4 flex flex-col items-start gap-2">
                                    {suggestionsFor(screen.id).map((s) => (
                                        <button key={s} type="button" onClick={() => agent.send(s)}
                                                className="text-left text-[13px] px-3 py-1.5 rounded-full border border-line-strong bg-white hover:bg-stone-50">
                                            {s}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    ) : agent.items.map((item) => <Row key={item.id} item={item} />)}
                    {thinking && (
                        <p className="flex items-center gap-2 text-[13px] text-stone-500"><Loader2 size={14} className="animate-spin" aria-hidden /> Thinking…</p>
                    )}
                </div>
            )}

            <div className="shrink-0 border-t border-line p-2.5">
                <div className="flex items-end gap-2 rounded-lg border border-line-strong bg-white px-2.5 py-1.5 focus-within:border-plum">
                    <textarea
                        ref={box}
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        onKeyDown={onKey}
                        rows={1}
                        maxLength={4000}
                        placeholder="Ask Nimmi…"
                        aria-label="Message Nimmi"
                        className="flex-1 resize-none bg-transparent text-[13.5px] leading-6 max-h-32 outline-none py-0.5 [field-sizing:content]"
                    />
                    {agent.running ? (
                        <button type="button" onClick={agent.stop} aria-label="Stop"
                                className="h-8 w-8 shrink-0 rounded-md bg-ink text-white flex items-center justify-center hover:bg-stone-700">
                            <Square size={12} fill="currentColor" />
                        </button>
                    ) : (
                        <button type="button" onClick={submit} disabled={!draft.trim() || agent.ready === false} aria-label="Send"
                                className="h-8 w-8 shrink-0 rounded-md bg-plum text-white flex items-center justify-center hover:bg-plum-hover disabled:opacity-40">
                            <ArrowUp size={16} />
                        </button>
                    )}
                </div>
                <p className="mt-1.5 px-1 text-[10.5px] text-stone-400">Nimmi can make mistakes; check anything important.<span className="hidden sm:inline"> Ctrl + / opens and closes it.</span></p>
            </div>
        </aside>
    );
}

function Row({ item }: { item: Item }) {
    const agent = useAgent()!;
    if (item.type === "user") {
        return <div className="flex justify-end"><p className="max-w-[85%] rounded-2xl rounded-br-md bg-plum-tint px-3 py-2 whitespace-pre-wrap [overflow-wrap:anywhere]">{item.text}</p></div>;
    }
    if (item.type === "step") {
        return (
            <p className="flex items-center gap-2 text-[12px] text-stone-500">
                {item.running ? <Loader2 size={13} className="animate-spin" aria-hidden />
                    : item.ok ? <Check size={13} className="text-emerald-600" aria-hidden />
                    : <CircleAlert size={13} className="text-amber-600" aria-hidden />}
                <span className={cn(item.undone && "line-through")}>{item.label}{!item.running && !item.ok ? " (didn't work)" : ""}</span>
                {item.undone && <span className="text-stone-400">Undone</span>}
                {item.undoable && !item.undone && (
                    <button type="button" onClick={() => agent.undo(item.actionId!)} disabled={item.busy}
                            className="ml-auto inline-flex items-center gap-1 text-[12px] font-medium text-plum hover:underline disabled:opacity-50">
                        <Undo2 size={12} aria-hidden /> Undo
                    </button>
                )}
            </p>
        );
    }
    if (item.type === "confirm") {
        const open = item.state === "proposed";
        const outcome: Record<string, string> = { done: "Done", cancelled: "Cancelled", expired: "Expired: ask again", failed: "Didn't work", confirming: "Working…" };
        return (
            <div className={cn("rounded-lg border px-3 py-2.5", open ? "border-plum/30 bg-plum-tint/60" : "border-line bg-stone-50")}>
                <p className="text-[13px] font-semibold">{item.title}</p>
                <p className="mt-0.5 text-[12.5px] text-stone-600">{item.summary}</p>
                {open ? (
                    <div className="mt-2.5 flex gap-2">
                        <button type="button" onClick={() => agent.decide(item.actionId, "confirm")} disabled={item.busy}
                                className="h-8 px-3 rounded-md bg-plum text-white text-[13px] font-medium hover:bg-plum-hover disabled:opacity-50">
                            {item.busy ? "Working…" : "Confirm"}
                        </button>
                        <button type="button" onClick={() => agent.decide(item.actionId, "cancel")} disabled={item.busy}
                                className="h-8 px-3 rounded-md border border-line-strong bg-white text-[13px] hover:bg-stone-50 disabled:opacity-50">
                            Cancel
                        </button>
                    </div>
                ) : (
                    <p className={cn("mt-1.5 text-[12px] font-medium", item.state === "done" ? "text-emerald-700" : item.state === "failed" ? "text-signal" : "text-stone-500")}>
                        {outcome[item.state] ?? item.state}{item.message && item.state === "failed" ? `: ${item.message}` : ""}
                    </p>
                )}
            </div>
        );
    }
    if (item.type === "card") {
        return <AgentCard card={item.card} active={item.active} busy={item.busy} />;
    }
    if (item.type === "note") {
        return <p className="text-[12px] text-stone-500 italic">{item.text.replace(/^\(|\)$/g, "")}</p>;
    }
    if (item.type === "error") {
        return <p role="alert" className="rounded-md border border-signal/20 bg-signal/5 px-3 py-2 text-[13px] text-signal">{item.text}</p>;
    }
    return item.text ? <AgentText text={item.text} /> : null;
}

function IconButton({ label, onClick, children, pressed, className }: {
    label: string; onClick: () => void; children: React.ReactNode; pressed?: boolean; className?: string;
}) {
    return (
        <button type="button" onClick={onClick} aria-label={label} title={label} aria-pressed={pressed}
                className={cn("h-8 w-8 shrink-0 rounded-md flex items-center justify-center text-stone-500 hover:text-ink hover:bg-stone-100",
                              pressed && "bg-stone-100 text-ink", className)}>
            {children}
        </button>
    );
}

type ActionRow = { id: string; summary: string; title?: string; state: string; by: string; mine: boolean; undoable: boolean; at: string };

/** What Nimmi changed in this workspace (owners and admins see everyone's), with Undo on one's own. */
function Changes() {
    const [rows, setRows] = useState<ActionRow[] | null>(null);
    const [today, setToday] = useState<{ used_today: number; daily_limit: number } | null>(null);
    const [error, setError] = useState("");
    const load = () => {
        apiJson<ActionRow[]>("/api/agent/actions").then(setRows).catch((e: Error) => { setRows([]); setError(e.message); });
        apiJson<{ used_today: number; daily_limit: number }>("/api/agent/status").then(setToday).catch(() => {});
    };
    useEffect(load, []);
    const decide = (id: string, choice: "confirm" | "cancel") => {
        apiJson<{ refresh?: { kind: string; id: string }[] }>(`/api/agent/actions/${id}/${choice}`, { method: "POST" })
            .then((r) => { r.refresh?.forEach(announceChange); load(); })
            .catch((e: Error) => setError(e.message));
    };
    const waiting = (rows ?? []).filter((r) => r.state === "proposed");
    const done = (rows ?? []).filter((r) => r.state !== "proposed");
    const undo = (id: string) => {
        apiJson<{ refresh?: { kind: string; id: string }[] }>(`/api/agent/actions/${id}/undo`, { method: "POST" })
            .then((r) => { r.refresh?.forEach(announceChange); load(); })
            .catch((e: Error) => setError(e.message));
    };
    return (
        <div className="px-1">
            {today && <p className="px-1 pb-2 text-[12px] text-stone-500">Today: {today.used_today} of {today.daily_limit} messages to Nimmi in this workspace.</p>}
            {error && <p role="alert" className="px-1 pb-2 text-[12px] text-signal">{error}</p>}
            {waiting.length > 0 && (
                <div className="mb-3">
                    <p className="px-1 pb-1.5 text-[12px] font-medium text-stone-600">Waiting for you</p>
                    {waiting.map((r) => (
                        <div key={r.id} className="rounded-lg border border-plum/30 bg-plum-tint/60 px-3 py-2.5 mb-2">
                            <p className="text-[13px] font-semibold">{r.title ?? "Confirm"}</p>
                            <p className="text-[12.5px] text-stone-600 mt-0.5">{r.summary}</p>
                            <div className="mt-2 flex gap-2">
                                <button type="button" onClick={() => decide(r.id, "confirm")} className="h-7 px-3 rounded-md bg-plum text-white text-[12.5px] font-medium hover:bg-plum-hover">Confirm</button>
                                <button type="button" onClick={() => decide(r.id, "cancel")} className="h-7 px-3 rounded-md border border-line-strong bg-white text-[12.5px] hover:bg-stone-50">Cancel</button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
            {rows === null ? <p className="px-1 py-3 text-[13px] text-stone-500">Loading…</p>
                : done.length === 0 ? <p className="px-1 py-3 text-[13px] text-stone-500">Nimmi hasn&apos;t changed anything yet.</p>
                : done.map((r) => (
                    <div key={r.id} className="flex items-start gap-2 px-1 py-2 border-b border-line last:border-0">
                        <div className="min-w-0 flex-1">
                            <p className={cn("text-[12.5px]", r.state === "undone" && "line-through text-stone-400")}>{r.summary}</p>
                            <p className="text-[11px] text-stone-500">
                                {new Date(r.at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}
                                {r.by ? ` · ${r.mine ? "you" : r.by}` : ""}{r.state === "undone" ? " · undone" : r.state === "failed" ? " · didn't work" : ""}
                            </p>
                        </div>
                        {r.undoable && (
                            <button type="button" onClick={() => undo(r.id)} className="shrink-0 inline-flex items-center gap-1 text-[12px] font-medium text-plum hover:underline">
                                <Undo2 size={12} aria-hidden /> Undo
                            </button>
                        )}
                    </div>
                ))}
        </div>
    );
}
