"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, BookmarkPlus, MessageCircle, Globe, Send, Settings } from "lucide-react";
import AppHeader from "@/components/AppHeader";
import { Button, EmptyState, Segmented, Skeleton, Status, ToastProvider, cn, useToast } from "@/components/ui";
import { LiveChatSettings, type SavedReply, type WorkspaceSettings } from "@/components/livechat/LiveChatSettings";
import { apiJson, currentUserId, getToken } from "@/lib/api";
import { liveSocket, refreshWaiting } from "@/lib/liveChat";
import { useApi } from "@/lib/useApi";
import { formatWhen } from "@/lib/voice/api";

type Lead = { score: number; label: "hot" | "warm" | "cold"; reasons: string[] };
type Handoff = {
    conversation_id: string;
    bot_id: string;
    bot_name: string;
    session_id: string;
    status: "pending" | "human";
    agent_id: string | null;
    created_at: string;
    captured_data: Record<string, string> | null;
    channel?: "web" | "whatsapp";
    lead?: Lead;
};
type Msg = { text: string; sender: "user" | "agent" | "system" | "note"; at: Date; author?: string | null };

const LEAD_TONE = { hot: "bad", warm: "warn", cold: "neutral" } as const;
const isLiveSession = (s: string) => s.startsWith("widget-session-human-") || s.startsWith("wa:");

export default function LiveChatPage() {
    return (
        <ToastProvider>
            <LiveChat />
        </ToastProvider>
    );
}

function LiveChat() {
    const router = useRouter();
    const toast = useToast();
    const [handoffs, setHandoffs] = useState<Handoff[] | null>(null);
    const [selected, setSelected] = useState<Handoff | null>(null);
    const [messages, setMessages] = useState<Msg[]>([]);
    const [unread, setUnread] = useState<Record<string, number>>({});
    const [input, setInput] = useState("");
    const [mode, setMode] = useState<"reply" | "note">("reply");
    const [showSettings, setShowSettings] = useState(false);
    const [picker, setPicker] = useState(false);
    const replies = useApi<SavedReply[]>("/api/workspace/replies");
    const workspace = useApi<WorkspaceSettings>("/api/workspace/settings");
    const selectedRef = useRef<Handoff | null>(null);
    const bottom = useRef<HTMLDivElement>(null);
    const box = useRef<HTMLTextAreaElement>(null);
    const me = useRef<string | null>(null);

    useEffect(() => { selectedRef.current = selected; }, [selected]);
    useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [messages]);

    const load = useCallback(async () => {
        try {
            const list = await apiJson<Handoff[]>("/api/handoffs/pending");
            setHandoffs(list.filter((h) => isLiveSession(h.session_id)));
        } catch (e) {
            toast((e as Error).message);
            setHandoffs((h) => h ?? []);
        }
    }, [toast]);

    useEffect(() => {
        me.current = currentUserId();
        if (!me.current) {
            router.push("/auth/login");
            return;
        }
        load();
        const socket = liveSocket();
        if (!socket) return;
        const onHandoff = () => load();
        const onMessage = (data: { room: string; message: string; sender: string }) => {
            const fromVisitor = data.sender !== "agent";
            if (selectedRef.current?.session_id === data.room) {
                setMessages((m) => [...m, { text: data.message, sender: fromVisitor ? "user" : "agent", at: new Date() }]);
            } else if (fromVisitor) {
                setUnread((u) => ({ ...u, [data.room]: (u[data.room] || 0) + 1 }));
            }
        };
        const onNote = (data: { conversation_id: string; content: string; author: string | null }) => {
            if (selectedRef.current?.conversation_id === data.conversation_id) {
                setMessages((m) => m.some((x) => x.sender === "note" && x.text === data.content && Date.now() - x.at.getTime() < 3000)
                    ? m : [...m, { text: data.content, sender: "note", at: new Date(), author: data.author }]);
            }
        };
        socket.on("handoff_requested", onHandoff);
        socket.on("message", onMessage);
        socket.on("note_added", onNote);
        return () => {
            socket.off("handoff_requested", onHandoff);
            socket.off("message", onMessage);
            socket.off("note_added", onNote);
        };
    }, [router, load]);

    const open = async (h: Handoff) => {
        try {
            await apiJson(`/api/handoffs/${h.conversation_id}/accept`, { method: "POST" });
        } catch (e) {
            toast((e as Error).message);
            return;
        }
        setSelected({ ...h, status: "human", agent_id: me.current });
        setUnread((u) => ({ ...u, [h.session_id]: 0 }));
        setMode("reply");
        liveSocket()?.emit("join", { room: h.session_id, token: getToken() });
        try {
            const history = await apiJson<{ content: string; role: string; timestamp: string | null; author: string | null }[]>(`/api/handoffs/${h.conversation_id}/messages`);
            setMessages([
                ...history.map((m) => ({
                    text: m.content, author: m.author, at: m.timestamp ? new Date(m.timestamp) : new Date(),
                    sender: (m.role === "user" ? "user" : m.role === "note" ? "note" : "agent") as Msg["sender"],
                })),
                { text: "You joined the conversation", sender: "system", at: new Date() },
            ]);
        } catch {
            setMessages([{ text: "You joined the conversation", sender: "system", at: new Date() }]);
        }
        refreshWaiting();
    };

    const send = async () => {
        const text = input.trim();
        if (!text || !selected) return;
        if (mode === "note") {
            try {
                const note = await apiJson<{ content: string; author: string | null }>(`/api/handoffs/${selected.conversation_id}/notes`, { method: "POST", json: { text } });
                setMessages((m) => [...m, { text: note.content, sender: "note", at: new Date(), author: note.author }]);
                setInput("");
            } catch (e) {
                toast((e as Error).message);
            }
            return;
        }
        liveSocket()?.emit("message", { room: selected.session_id, message: text, sender: "agent" });
        setInput("");
    };

    const resolve = async () => {
        if (!selected) return;
        try {
            await apiJson(`/api/handoffs/${selected.conversation_id}/close`, { method: "POST" });
            toast("Resolved. The assistant takes over from here.");
            setSelected(null);
            setMessages([]);
            load();
            refreshWaiting();
        } catch (e) {
            toast((e as Error).message);
        }
    };

    // "/" at the start of the reply opens saved replies, filtered by what follows.
    const slash = input.startsWith("/") ? input.slice(1).toLowerCase() : null;
    const matches = useMemo(() => {
        const q = slash ?? "";
        return (replies.data ?? []).filter((r) => !q || r.title.toLowerCase().includes(q) || r.body.toLowerCase().includes(q)).slice(0, 8);
    }, [replies.data, slash]);
    const showPicker = (picker || slash !== null) && mode === "reply";
    const applyReply = (r: SavedReply) => {
        const name = (selected?.captured_data?.name || selected?.captured_data?.Name || "").split(" ")[0];
        setInput(r.body.replace(/\{\{\s*name\s*\}\}/gi, name || "there"));
        setPicker(false);
        requestAnimationFrame(() => box.current?.focus());
    };

    const details = Object.entries(selected?.captured_data ?? {}).filter(([k]) => k !== "channel");
    const ws = workspace.data;

    return (
        <div className="min-h-screen bg-paper text-ink flex flex-col">
            <AppHeader />
            <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col">
                <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
                    <div>
                        <h1 className="text-2xl font-semibold tracking-tight">Live chat</h1>
                        <p className="text-sm text-stone-500 mt-1">People who asked for a person on your website or WhatsApp. Reply here; they see it where they wrote.</p>
                    </div>
                    <div className="flex items-center gap-3">
                        {ws && (
                            <Status tone={ws.open_now ? "good" : "warn"}>
                                {ws.business_hours.enabled ? (ws.open_now ? "Open now" : `Closed, back ${ws.next_open}`) : "Always open"}
                            </Status>
                        )}
                        <Button size="sm" onClick={() => setShowSettings(true)}><Settings size={14} /> Settings</Button>
                    </div>
                </div>

                <div className="flex-1 min-h-[560px] grid md:grid-cols-[300px_minmax(0,1fr)] bg-white border border-line rounded-lg overflow-hidden">
                    {/* Inbox */}
                    <aside className={cn("border-r border-line flex flex-col min-h-0", selected && "hidden md:flex")}>
                        <div className="px-4 py-3 border-b border-line text-[13px] text-stone-500">
                            {handoffs ? `${handoffs.length} ${handoffs.length === 1 ? "conversation" : "conversations"}` : "Loading…"}
                        </div>
                        <ul className="flex-1 overflow-y-auto">
                            {handoffs === null && <li className="p-4 space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</li>}
                            {handoffs?.length === 0 && (
                                <li><EmptyState title="Nobody is waiting" body="When someone asks for a person, on your website or WhatsApp, they show up here." /></li>
                            )}
                            {handoffs?.map((h) => {
                                const name = h.captured_data?.name || h.captured_data?.Name;
                                const takenByOther = h.status === "human" && h.agent_id && h.agent_id !== me.current;
                                const wa = h.channel === "whatsapp" || h.session_id.startsWith("wa:");
                                const ChannelIcon = wa ? MessageCircle : Globe;
                                return (
                                    <li key={h.conversation_id}>
                                        <button
                                            onClick={() => open(h)}
                                            className={cn(
                                                "w-full text-left px-4 py-3 border-b border-line transition-colors",
                                                selected?.conversation_id === h.conversation_id ? "bg-plum-tint" : "hover:bg-stone-50",
                                            )}
                                        >
                                            <div className="flex items-center gap-2">
                                                <ChannelIcon size={13} className="text-stone-400 shrink-0" aria-label={wa ? "WhatsApp" : "Website"} />
                                                <span className="text-sm font-medium truncate flex-1">{name || (wa ? `+${h.session_id.slice(3)}` : `Visitor ${h.session_id.slice(-5)}`)}</span>
                                                {(unread[h.session_id] || 0) > 0 && (
                                                    <span className="min-w-5 h-5 px-1.5 rounded-full bg-signal text-white text-[11px] tabular-nums inline-flex items-center justify-center">
                                                        {unread[h.session_id]}
                                                    </span>
                                                )}
                                            </div>
                                            <div className="flex items-center justify-between gap-2 mt-1">
                                                <span className="text-xs text-stone-500 truncate">{h.bot_name}</span>
                                                <span className="text-xs text-stone-400 whitespace-nowrap">{formatWhen(h.created_at)}</span>
                                            </div>
                                            <div className="mt-1.5 flex items-center gap-3">
                                                {h.status === "pending"
                                                    ? <Status tone="bad">Waiting</Status>
                                                    : <Status tone="neutral">{takenByOther ? "With a teammate" : "With you"}</Status>}
                                                {h.lead && h.lead.label !== "cold" && (
                                                    <span title={h.lead.reasons.join(", ")}><Status tone={LEAD_TONE[h.lead.label]}>{h.lead.label === "hot" ? "Hot lead" : "Warm lead"}</Status></span>
                                                )}
                                            </div>
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    </aside>

                    {/* Conversation */}
                    <section className={cn("flex flex-col min-h-0", !selected && "hidden md:flex")}>
                        {selected ? (
                            <>
                                <div className="flex items-center gap-3 px-4 py-3 border-b border-line">
                                    <button onClick={() => setSelected(null)} className="md:hidden p-1 -ml-1 text-stone-500" aria-label="Back to conversations">
                                        <ArrowLeft size={18} />
                                    </button>
                                    <div className="min-w-0 flex-1">
                                        <p className="text-sm font-medium truncate">{selected.captured_data?.name || selected.captured_data?.Name || (selected.session_id.startsWith("wa:") ? `+${selected.session_id.slice(3)}` : `Visitor ${selected.session_id.slice(-5)}`)}</p>
                                        <p className="text-xs text-stone-500 truncate">{selected.bot_name} · {selected.session_id.startsWith("wa:") ? "WhatsApp" : "Website chat"}</p>
                                    </div>
                                    <Button size="sm" onClick={resolve}>Resolve</Button>
                                </div>

                                {details.length > 0 && (
                                    <dl className="flex flex-wrap gap-x-6 gap-y-1 px-4 py-2.5 border-b border-line bg-stone-50/60 text-xs">
                                        {details.map(([k, v]) => (
                                            <div key={k} className="flex gap-1.5"><dt className="text-stone-500">{k}</dt><dd>{v}</dd></div>
                                        ))}
                                    </dl>
                                )}

                                <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3" aria-live="polite">
                                    {messages.map((m, i) => m.sender === "system" ? (
                                        <p key={i} className="text-center text-xs text-stone-400">{m.text}</p>
                                    ) : m.sender === "note" ? (
                                        <div key={i} className="mx-auto max-w-[85%] px-3.5 py-2 rounded-md bg-amber-50 border border-amber-200 text-sm leading-relaxed whitespace-pre-wrap">
                                            <span className="block text-[11px] text-amber-800 mb-0.5">Note{m.author ? ` from ${m.author}` : ""} · only your team sees this</span>
                                            {m.text}
                                        </div>
                                    ) : (
                                        <div key={i} className={cn("flex", m.sender === "agent" ? "justify-end" : "justify-start")}>
                                            <div className={cn(
                                                "max-w-[75%] px-3.5 py-2 rounded-lg text-sm leading-relaxed whitespace-pre-wrap",
                                                m.sender === "agent" ? "bg-plum text-white rounded-br-sm" : "bg-stone-100 text-ink rounded-bl-sm",
                                            )}>
                                                {m.text}
                                            </div>
                                        </div>
                                    ))}
                                    <div ref={bottom} />
                                </div>

                                <div className="relative border-t border-line">
                                    {showPicker && (
                                        <div className="absolute bottom-full left-3 right-3 mb-2 max-h-64 overflow-y-auto bg-white border border-line rounded-lg shadow-[0_12px_40px_rgba(28,23,25,0.14)] z-10">
                                            {matches.length === 0 ? (
                                                <p className="px-3 py-3 text-[13px] text-stone-500">
                                                    {replies.data?.length ? "No saved reply matches." : "No saved replies yet. Add them in Settings."}
                                                </p>
                                            ) : matches.map((r) => (
                                                <button key={r.id} type="button" onClick={() => applyReply(r)}
                                                        className="w-full text-left px-3 py-2 hover:bg-stone-50 border-t border-line first:border-t-0">
                                                    <span className="block text-[13px] font-medium">{r.title}</span>
                                                    <span className="block text-xs text-stone-500 truncate">{r.body}</span>
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                    <div className="flex items-center gap-2 px-3 pt-2.5">
                                        <Segmented label="Message type" value={mode} onChange={(v) => { setMode(v); setPicker(false); }}
                                                   options={[{ value: "reply", label: "Reply" }, { value: "note", label: "Internal note" }]} />
                                        {mode === "reply" && (
                                            <button type="button" onClick={() => setPicker((p) => !p)} aria-expanded={showPicker}
                                                    className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md text-[13px] text-stone-600 hover:bg-stone-100">
                                                <BookmarkPlus size={13} /> Saved replies
                                            </button>
                                        )}
                                    </div>
                                    <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex items-end gap-2 p-3">
                                        <textarea
                                            ref={box}
                                            value={input}
                                            onChange={(e) => setInput(e.target.value)}
                                            onKeyDown={(e) => {
                                                if (e.key === "Escape") setPicker(false);
                                                if (e.key === "Enter" && !e.shiftKey) {
                                                    e.preventDefault();
                                                    if (showPicker && slash !== null && matches[0]) applyReply(matches[0]);
                                                    else send();
                                                }
                                            }}
                                            placeholder={mode === "note" ? "Add a note for your team. The customer won't see it." : "Write a reply, or type / for saved replies."}
                                            rows={1}
                                            aria-label={mode === "note" ? "Internal note" : "Reply"}
                                            className={cn(
                                                "flex-1 resize-none max-h-32 border rounded-md px-3 py-2 text-sm placeholder:text-stone-400 focus:outline-none focus:ring-2",
                                                mode === "note" ? "bg-amber-50 border-amber-200 focus:border-amber-400 focus:ring-amber-200/40"
                                                    : "bg-white border-line-strong focus:border-plum focus:ring-plum/15",
                                            )}
                                        />
                                        <Button type="submit" variant="primary" aria-label={mode === "note" ? "Add note" : "Send"} disabled={!input.trim()}><Send size={15} /></Button>
                                    </form>
                                </div>
                            </>
                        ) : (
                            <div className="flex-1 flex items-center justify-center p-8">
                                <EmptyState title="Pick a conversation" body="Choose someone from the list to read their chat and reply." />
                            </div>
                        )}
                    </section>
                </div>
            </main>

            <LiveChatSettings open={showSettings} onClose={() => setShowSettings(false)}
                              onSaved={(s) => workspace.setData(s)} replies={replies.data} onRepliesChange={replies.reload} />
        </div>
    );
}
