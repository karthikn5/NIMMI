"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { usePathname } from "next/navigation";
import { Ellipsis, Eye, History, Keyboard, PanelRight, PictureInPicture2, Plus, Trash2, Undo2, X } from "lucide-react";
import { cn } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { announceChange } from "@/lib/agent/changes";
import { useSpeaker } from "@/lib/agent/useSpeaker";
import AgentComposer, { type ComposerAction, type ComposerHandle } from "./AgentComposer";
import { NimmiTurn, UserMessage, Welcome } from "./AgentMessages";
import { useAgent, type Item } from "./AgentProvider";

/** The agent's panel: docked beside the page on wide screens, floating otherwise, a sheet from the bottom on phones. */
export default function AgentPanel({ docked }: { docked: boolean }) {
    const agent = useAgent()!;
    const pathname = usePathname();
    const [showHistory, setShowHistory] = useState(false);
    const [showShared, setShowShared] = useState(false);
    const [showMenu, setShowMenu] = useState(false);
    const [showKeys, setShowKeys] = useState(false);
    const [historyTab, setHistoryTab] = useState<"chats" | "changes">("chats");
    const [listening, setListening] = useState(false);
    const [notice, setNotice] = useState("");
    const [screen, setScreen] = useState(() => agent.screen());
    const list = useRef<HTMLDivElement>(null);
    const composer = useRef<ComposerHandle>(null);
    const menu = useRef<HTMLDivElement>(null);
    const atBottom = useRef(true);
    const speaker = useSpeaker((message) => setNotice(message));

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

    useEffect(() => { composer.current?.focus(); }, []);
    useEffect(() => { if (!notice) return; const t = setTimeout(() => setNotice(""), 6000); return () => clearTimeout(t); }, [notice]);
    useEffect(() => {
        if (!showMenu) return;
        const away = (e: MouseEvent) => { if (!menu.current?.contains(e.target as Node)) setShowMenu(false); };
        document.addEventListener("mousedown", away);
        return () => document.removeEventListener("mousedown", away);
    }, [showMenu]);

    const send = (text: string) => {
        agent.send(text);
        atBottom.current = true;
        setShowHistory(false);
        setShowKeys(false);
    };
    const act = (action: ComposerAction) => {
        if (action === "new") { agent.newChat(); setShowHistory(false); }
        if (action === "changes") { setHistoryTab("changes"); setShowHistory(true); }
        if (action === "shortcuts") setShowKeys(true);
        setShowMenu(false);
    };
    const onPanelKey = (e: KeyboardEvent<HTMLElement>) => {
        if (e.key !== "Escape") return;
        if (showMenu || showKeys) { setShowMenu(false); setShowKeys(false); return; }
        if (!docked) agent.close();
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
    // The conversation in turns: each message of theirs, then everything Nimmi did and said in reply.
    const turns = useMemo(() => {
        const out: { kind: "user" | "nimmi"; items: Item[] }[] = [];
        for (const item of agent.items) {
            const kind = item.type === "user" ? "user" : "nimmi";
            const last = out[out.length - 1];
            if (kind === "nimmi" && last?.kind === "nimmi") last.items.push(item);
            else out.push({ kind, items: [item] });
        }
        return out;
    }, [agent.items]);
    const working = [...agent.items].reverse().find((i) => i.type === "step" && i.running);
    const lastItem = agent.items[agent.items.length - 1];
    const thinking = agent.running && (!lastItem || lastItem.type === "user" || lastItem.type === "note" || lastItem.type === "plan"
                                       || (lastItem.type === "step" && !lastItem.running));
    // While a task runs: the step of its plan being worked on, and how far along it is.
    const plan = agent.running ? [...agent.items].reverse().find((i) => i.type === "plan") : undefined;
    const current = plan?.type === "plan" ? plan.steps.findIndex((s) => s.status === "doing") : -1;
    const status = listening ? "Listening…" : agent.running
        ? (agent.waitingNote ? agent.waitingNote
            : working && working.type === "step" ? `${working.label}…`
            : plan?.type === "plan" && current >= 0 ? `Step ${current + 1} of ${plan.steps.length}: ${plan.steps[current].title}`
            : "Thinking…")
        : agent.ready === false ? "Not set up on this server" : "Ready to help";

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
                <span className="relative shrink-0">
                    <img src="/agent/nimmi.svg" alt="" className="h-8 w-8 rounded-full border border-line" />
                    <span className={cn("absolute -right-0.5 -bottom-0.5 h-2.5 w-2.5 rounded-full border-2 border-white",
                                        listening ? "bg-signal animate-pulse" : agent.running ? "bg-amber-500 animate-pulse" : agent.ready === false ? "bg-stone-300" : "bg-emerald-500")} aria-hidden />
                </span>
                <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold leading-tight">Nimmi</p>
                    <p className="text-[11px] text-stone-500 leading-tight truncate" aria-live="polite">{status}</p>
                </div>
                <IconButton label="Past chats" pressed={showHistory && historyTab === "chats"}
                            onClick={() => { const show = !(showHistory && historyTab === "chats"); setHistoryTab("chats"); setShowHistory(show); if (show) agent.loadThreads(); }}>
                    <History size={16} />
                </IconButton>
                <IconButton label="New chat" onClick={() => act("new")}><Plus size={16} /></IconButton>
                <div ref={menu} className="relative">
                    <IconButton label="More" pressed={showMenu} onClick={() => setShowMenu((m) => !m)}><Ellipsis size={16} /></IconButton>
                    {showMenu && (
                        <div role="menu" className="absolute right-0 top-9 z-20 w-56 rounded-lg border border-line bg-white py-1 text-[13px] shadow-[0_12px_32px_rgba(28,23,25,0.14)]">
                            {agent.canDock && (
                                <MenuItem icon={docked ? PictureInPicture2 : PanelRight} onClick={() => { agent.setDocked(!docked); setShowMenu(false); }}>
                                    {docked ? "Float the panel" : "Dock beside the page"}
                                </MenuItem>
                            )}
                            <MenuItem icon={History} onClick={() => act("changes")}>What Nimmi changed</MenuItem>
                            <MenuItem icon={Keyboard} onClick={() => act("shortcuts")}>Keyboard shortcuts</MenuItem>
                            {agent.threadId && (
                                <MenuItem icon={Trash2} danger onClick={() => { agent.deleteThread(agent.threadId!); setShowMenu(false); }}>Delete this chat</MenuItem>
                            )}
                        </div>
                    )}
                </div>
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

            {showKeys ? (
                <div className="flex-1 overflow-y-auto px-4 py-4">
                    <div className="flex items-center justify-between">
                        <p className="text-[13px] font-semibold">Keyboard shortcuts</p>
                        <button type="button" onClick={() => setShowKeys(false)} className="text-[12px] text-plum hover:underline">Done</button>
                    </div>
                    <dl className="mt-3 divide-y divide-line text-[12.5px]">
                        {[["Ctrl + /", "Open or close Nimmi"], ["Enter", "Send"], ["Shift + Enter", "New line"], ["/", "Shortcuts: explain, change, build, connect"],
                          ["↑ ↓ then Enter", "Pick a shortcut"], ["Esc", "Close a menu, or the floating panel"]].map(([k, v]) => (
                            <div key={k} className="flex items-center justify-between gap-3 py-2">
                                <dt className="text-stone-600">{v}</dt>
                                <dd><kbd className="rounded border border-line-strong bg-stone-50 px-1.5 py-0.5 font-mono text-[11px]">{k}</kbd></dd>
                            </div>
                        ))}
                    </dl>
                </div>
            ) : showHistory ? (
                <div className="flex-1 overflow-y-auto p-2">
                    <div role="tablist" className="flex gap-1 px-1 pb-2">
                        {(["chats", "changes"] as const).map((t) => (
                            <button key={t} type="button" role="tab" aria-selected={historyTab === t} onClick={() => { setHistoryTab(t); if (t === "chats") agent.loadThreads(); }}
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
                     className="flex-1 overflow-y-auto px-3 py-4 space-y-4 text-[13.5px] leading-relaxed">
                    {agent.items.length === 0 ? (
                        agent.ready === false ? (
                            <p className="pt-4 text-[13px] text-signal">Nimmi isn&apos;t set up on this server yet: it needs an AI service key.</p>
                        ) : <Welcome name={name} screenId={screen.id} onSend={send} onFill={(t) => composer.current?.fill(t)} />
                    ) : turns.map((turn, i) => turn.kind === "user"
                        ? <UserMessage key={turn.items[0].id} text={(turn.items[0] as Extract<Item, { type: "user" }>).text} />
                        : <NimmiTurn key={turn.items[0].id} items={turn.items} latest={i === turns.length - 1} speaker={speaker} working={agent.running} />)}
                    {thinking && (
                        <div className="flex items-center gap-2.5 text-[13px] text-stone-500">
                            <img src="/agent/nimmi.svg" alt="" className="h-6 w-6 rounded-full border border-line" />
                            <span className="inline-flex gap-1" aria-label="Thinking">
                                {[0, 1, 2].map((d) => <span key={d} className="h-1.5 w-1.5 rounded-full bg-stone-400 animate-bounce" style={{ animationDelay: `${d * 150}ms` }} />)}
                            </span>
                        </div>
                    )}
                </div>
            )}

            {notice && <p role="alert" className="shrink-0 mx-3 mb-1 rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-[12px] text-amber-900">{notice}</p>}
            <AgentComposer ref={composer} running={agent.running} disabled={agent.ready === false} onSend={send} onStop={agent.stop}
                           onAction={act} onError={setNotice} onListening={setListening} />
        </aside>
    );
}

function MenuItem({ icon: Icon, onClick, children, danger }: {
    icon: typeof History; onClick: () => void; children: React.ReactNode; danger?: boolean;
}) {
    return (
        <button type="button" role="menuitem" onClick={onClick}
                className={cn("w-full flex items-center gap-2.5 px-3 py-1.5 text-left hover:bg-stone-50", danger ? "text-signal" : "text-stone-700 hover:text-ink")}>
            <Icon size={14} aria-hidden /> {children}
        </button>
    );
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
