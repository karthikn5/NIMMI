"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, ArrowLeft, BookmarkPlus, Check, CheckCheck, FileText, Paperclip, Search, Send } from "lucide-react";
import { Button, EmptyState, Input, Segmented, Select, Skeleton, Status, cn, useToast } from "@/components/ui";
import type { SavedReply } from "@/components/livechat/LiveChatSettings";
import { apiJson, apiUrl, currentUserId } from "@/lib/api";
import { liveSocket } from "@/lib/liveChat";
import { useApi } from "@/lib/useApi";
import { formatWhen } from "@/lib/voice/api";
import { fileKind, timeLeft, type Person, type WaChat, type WaChatDetail, type WaFile, type WaMessage, type WaNumber } from "@/lib/whatsapp";

type View = "open" | "ai" | "person" | "mine" | "closed";
const VIEWS: { value: View; label: string }[] = [
    { value: "open", label: "All" },
    { value: "person", label: "Waiting" },
    { value: "ai", label: "Assistant" },
    { value: "mine", label: "Mine" },
    { value: "closed", label: "Closed" },
];
const viewOf = (v: string | null): View => (VIEWS.some((x) => x.value === v) ? (v as View) : "open");

export default function InboxPage() {
    return <Suspense><Inbox /></Suspense>;
}

/** Every WhatsApp chat: the assistant answers on its own; the team reads along, steps in, and hands back. */
function Inbox() {
    const toast = useToast();
    const router = useRouter();
    const pathname = usePathname();
    const params = useSearchParams();
    const view = viewOf(params.get("view"));
    const openId = params.get("chat");
    const [typed, setTyped] = useState("");
    const [q, setQ] = useState("");
    const [numberId, setNumberId] = useState("");
    const [list, setList] = useState<WaChat[] | null>(null);
    const [chat, setChat] = useState<WaChatDetail | null>(null);
    const numbers = useApi<WaNumber[]>("/api/whatsapp/numbers");
    const people = useApi<Person[]>("/api/whatsapp/people");
    const files = useApi<WaFile[]>("/api/whatsapp/files");
    const replies = useApi<SavedReply[]>("/api/workspace/replies");
    const openRef = useRef<string | null>(null);
    useEffect(() => { openRef.current = openId; }, [openId]);
    useEffect(() => { const t = setTimeout(() => setQ(typed.trim()), 300); return () => clearTimeout(t); }, [typed]);

    const go = useCallback((next: { view?: View; chat?: string | null }) => {
        const p = new URLSearchParams(params.toString());
        if (next.view) p.set("view", next.view);
        if (next.chat === null) p.delete("chat");
        else if (next.chat) p.set("chat", next.chat);
        router.replace(`${pathname}?${p.toString()}`);
    }, [params, pathname, router]);

    const loadList = useCallback(async () => {
        try {
            setList(await apiJson<WaChat[]>(`/api/whatsapp/chats?view=${view}&q=${encodeURIComponent(q)}&number_id=${numberId}`));
        } catch (e) {
            toast((e as Error).message);
            setList((l) => l ?? []);
        }
    }, [view, q, numberId, toast]);

    const loadChat = useCallback(async (id: string, markRead = false) => {
        try {
            const detail = await apiJson<WaChatDetail>(`/api/whatsapp/chats/${id}`);
            if (openRef.current === id) setChat(detail);
            if (markRead && detail.unread) {
                await apiJson(`/api/whatsapp/chats/${id}/read`, { method: "POST" });
                setList((l) => l?.map((c) => (c.id === id ? { ...c, unread: 0 } : c)) ?? l);
            }
        } catch (e) {
            toast((e as Error).message);
        }
    }, [toast]);

    useEffect(() => { loadList(); }, [loadList]);
    useEffect(() => {
        setChat(null);
        if (openId) loadChat(openId, true);
    }, [openId, loadChat]);

    // Live updates, plus a re-read every few seconds: the socket may be on another server process than the message.
    useEffect(() => {
        const socket = liveSocket();
        const onMessage = (d: { chat: WaChat; message: WaMessage }) => {
            setList((l) => {
                if (!l) return l;
                const last = { role: d.message.role, text: d.message.text, by: d.message.sent_by === "customer" ? "customer" : d.message.sent_by === "ai" ? "ai" : "team" } as WaChat["last"];
                const updated = { ...(l.find((c) => c.id === d.chat.id) ?? {}), ...d.chat, last: d.message.role === "note" ? l.find((c) => c.id === d.chat.id)?.last ?? null : last };
                return [updated as WaChat, ...l.filter((c) => c.id !== d.chat.id)];
            });
            if (openRef.current === d.chat.id) {
                setChat((c) => (c && !c.messages.some((m) => m.id === d.message.id) ? { ...c, ...d.chat, messages: [...c.messages, d.message] } : c));
            }
        };
        const onStatus = (d: { chat_id: string; message_id: string; status: WaMessage["status"]; error: string | null }) => {
            if (openRef.current !== d.chat_id) return;
            setChat((c) => c && { ...c, messages: c.messages.map((m) => (m.id === d.message_id ? { ...m, status: d.status, error: d.error } : m)) });
        };
        const onChat = (d: { chat: WaChat }) => {
            setList((l) => l?.map((c) => (c.id === d.chat.id ? { ...c, ...d.chat } : c)) ?? l);
            if (openRef.current === d.chat.id) setChat((c) => c && { ...c, ...d.chat });
        };
        socket?.on("wa_message", onMessage);
        socket?.on("wa_status", onStatus);
        socket?.on("wa_chat", onChat);
        const timer = setInterval(() => {
            if (document.visibilityState !== "visible") return;
            loadList();
            if (openRef.current) loadChat(openRef.current);
        }, 6000);
        return () => {
            socket?.off("wa_message", onMessage);
            socket?.off("wa_status", onStatus);
            socket?.off("wa_chat", onChat);
            clearInterval(timer);
        };
    }, [loadList, loadChat]);

    const multiNumber = (numbers.data?.length ?? 0) > 1;
    const noNumber = numbers.data !== null && numbers.data.length === 0;

    return (
        <div className="min-h-[600px] h-[calc(100vh-260px)] grid md:grid-cols-[344px_minmax(0,1fr)] bg-white border border-line rounded-lg overflow-hidden">
            <aside className={cn("border-r border-line flex flex-col min-h-0", openId && "hidden md:flex")}>
                <div className="p-3 border-b border-line space-y-2.5">
                    <div className="overflow-x-auto [scrollbar-width:none] [&_button]:whitespace-nowrap [&_button]:shrink-0">
                        <Segmented<View> label="Which chats" value={view} onChange={(v) => go({ view: v })} options={VIEWS} />
                    </div>
                    <div className="flex gap-2">
                        <div className="relative flex-1">
                            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-stone-400" aria-hidden />
                            <Input aria-label="Search chats" className="pl-8 h-8 text-[13px]" placeholder="Name or number" value={typed} onChange={(e) => setTyped(e.target.value)} />
                        </div>
                        {multiNumber && (
                            <Select aria-label="WhatsApp number" className="w-auto h-8 text-[13px]" value={numberId} onChange={(e) => setNumberId(e.target.value)}>
                                <option value="">All numbers</option>
                                {numbers.data?.map((n) => <option key={n.id} value={n.id}>{n.display_number ?? n.phone_number_id}</option>)}
                            </Select>
                        )}
                    </div>
                </div>
                <ul className="flex-1 overflow-y-auto">
                    {list === null && <li className="p-4 space-y-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</li>}
                    {list?.length === 0 && (
                        <li>
                            <EmptyState
                                title={noNumber ? "No WhatsApp number yet" : q ? "No chats match" : view === "person" ? "Nobody is waiting for a person" : "No chats here yet"}
                                body={noNumber ? "Connect your number in Settings, then customers' chats appear here." : q ? "Try part of their name or number."
                                    : view === "person" ? "Chats where someone asked for a person, or your team is handling it, appear here."
                                    : "When customers message your WhatsApp number, their chats appear here."} />
                        </li>
                    )}
                    {list?.map((c) => <ChatRow key={c.id} c={c} active={c.id === openId} onOpen={() => go({ chat: c.id })} />)}
                </ul>
            </aside>

            <section className={cn("flex flex-col min-h-0", !openId && "hidden md:flex")}>
                {openId && chat ? (
                    <Thread key={chat.id} chat={chat} people={people.data ?? []} files={files.data ?? []} replies={replies.data ?? []}
                            onBack={() => go({ chat: null })}
                            onChange={(c) => { setChat((prev) => prev && { ...prev, ...c }); setList((l) => l?.map((x) => (x.id === c.id ? { ...x, ...c } : x)) ?? l); }}
                            onSent={(m) => setChat((prev) => prev && (prev.messages.some((x) => x.id === m.id) ? prev : { ...prev, messages: [...prev.messages, m] }))} />
                ) : openId ? (
                    <div className="p-6 space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>
                ) : (
                    <div className="flex-1 flex items-center justify-center p-8">
                        <EmptyState title="Pick a chat" body="Read what the assistant said, step in when you need to, and hand it back when you're done." />
                    </div>
                )}
            </section>
        </div>
    );
}

function needsPerson(c: WaChat): boolean {
    return c.handoff === "pending" || c.handoff === "human" || !!c.ai_paused_until;
}

function ChatRow({ c, active, onOpen }: { c: WaChat; active: boolean; onOpen: () => void }) {
    const by = c.last?.by === "ai" ? "Assistant: " : c.last?.by === "team" ? "You: " : "";
    return (
        <li>
            <button type="button" onClick={onOpen} aria-current={active ? "true" : undefined}
                    className={cn("w-full text-left px-4 py-3 border-b border-line transition-colors", active ? "bg-plum-tint" : "hover:bg-stone-50")}>
                <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate flex-1">{c.name}</span>
                    <span className="text-xs text-stone-400 whitespace-nowrap">{c.last_message_at ? formatWhen(c.last_message_at) : ""}</span>
                </div>
                <div className="flex items-center gap-2 mt-1">
                    <span className="text-[13px] text-stone-500 truncate flex-1">{by}{c.last?.text ?? ""}</span>
                    {c.unread > 0 && (
                        <span className="min-w-5 h-5 px-1.5 rounded-full bg-signal text-white text-[11px] tabular-nums inline-flex items-center justify-center" aria-label={`${c.unread} unread`}>
                            {c.unread}
                        </span>
                    )}
                </div>
                {(needsPerson(c) || c.status === "closed") && (
                    <div className="mt-1.5">
                        {c.status === "closed" ? <Status tone="neutral">Closed</Status>
                            : c.handoff === "pending" ? <Status tone="bad">Asked for a person</Status> : <Status tone="plum">Your team is handling it</Status>}
                    </div>
                )}
            </button>
        </li>
    );
}

function Thread({ chat, people, files, replies, onBack, onChange, onSent }: {
    chat: WaChatDetail; people: Person[]; files: WaFile[]; replies: SavedReply[];
    onBack: () => void; onChange: (c: WaChat) => void; onSent: (m: WaMessage) => void;
}) {
    const toast = useToast();
    const bottom = useRef<HTMLDivElement>(null);
    const [busy, setBusy] = useState(false);
    const count = chat.messages.length;
    useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [count]);
    const team = chat.handoff !== "ai" || !!chat.ai_paused_until;
    const left = timeLeft(chat.window_ends);
    const details = Object.entries(chat.captured ?? {}).filter(([k, v]) => k !== "channel" && v);

    const act = async (path: string, body?: unknown, done?: string) => {
        setBusy(true);
        try {
            onChange(await apiJson<WaChat>(`/api/whatsapp/chats/${chat.id}/${path}`, { method: "POST", json: body ?? {} }));
            if (done) toast(done);
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    return (
        <>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 border-b border-line">
                <button onClick={onBack} className="md:hidden p-1 -ml-1 text-stone-500" aria-label="Back to chats"><ArrowLeft size={18} /></button>
                <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium truncate">{chat.name}</p>
                    <p className="text-xs text-stone-500 truncate">
                        {[chat.phone, chat.number?.display_number ? `to ${chat.number.display_number}` : null].filter(Boolean).join(" · ")}
                    </p>
                </div>
                <Select aria-label="Assigned to" className="w-auto h-8 text-[13px]" value={chat.assigned_to ?? ""} disabled={busy}
                        onChange={(e) => act("assign", { user_id: e.target.value || null })}>
                    <option value="">Unassigned</option>
                    {people.map((p) => <option key={p.id} value={p.id}>{p.id === currentUserId() ? `${p.name} (you)` : p.name}</option>)}
                </Select>
                {team
                    ? <Button size="sm" disabled={busy} onClick={() => act("resume", undefined, "The assistant answers their next message.")}>Hand back to assistant</Button>
                    : <Button size="sm" disabled={busy} onClick={() => act("pause", undefined, "The assistant leaves this chat to you.")}>Take over</Button>}
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => act("status", { status: chat.status === "closed" ? "open" : "closed" })}>
                    {chat.status === "closed" ? "Reopen" : "Close"}
                </Button>
            </div>

            <div className={cn("px-4 py-2 border-b border-line text-xs flex flex-wrap gap-x-5 gap-y-1", team ? "bg-plum-tint/60" : "bg-stone-50/60")}>
                <span className="text-stone-600">
                    {chat.handoff === "pending" ? "They asked for a person. Reply to take over." : team ? "Your team is handling this chat: the assistant won't reply." : "The assistant is answering this chat."}
                </span>
                {details.map(([k, v]) => <span key={k} className="text-stone-500">{k}: <span className="text-ink">{v}</span></span>)}
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3" aria-live="polite">
                {chat.messages.length === 0 && <p className="text-center text-xs text-stone-400">No messages yet.</p>}
                {chat.messages.map((m) => <Bubble key={m.id} m={m} />)}
                <div ref={bottom} />
            </div>

            <Composer chat={chat} files={files} replies={replies} windowLeft={left} onSent={onSent} />
        </>
    );
}

function Ticks({ m }: { m: WaMessage }) {
    if (m.status === "read") return <CheckCheck size={14} className="text-sky-600" aria-label="Read" />;
    if (m.status === "delivered") return <CheckCheck size={14} className="text-stone-400" aria-label="Delivered" />;
    if (m.status === "sent") return <Check size={14} className="text-stone-400" aria-label="Sent" />;
    return null;
}

function Media({ m }: { m: WaMessage }) {
    const media = m.media;
    if (!media?.url) return null;
    const src = apiUrl(media.url);
    if (m.kind === "image" || m.kind === "sticker") {
        // eslint-disable-next-line @next/next/no-img-element
        return <img src={src} alt={media.caption || "Photo"} className="max-h-64 max-w-full rounded-md mb-1.5" />;
    }
    if (m.kind === "voice" || m.kind === "audio") return <audio controls src={src} className="max-w-full mb-1.5" />;
    if (m.kind === "video") return <video controls src={src} className="max-h-64 max-w-full rounded-md mb-1.5" />;
    return (
        <a href={src} target="_blank" rel="noopener noreferrer"
           className="flex items-center gap-2 mb-1.5 px-3 py-2 rounded-md bg-white/70 border border-line text-ink hover:border-line-strong">
            <FileText size={16} className="text-stone-500 shrink-0" aria-hidden />
            <span className="text-[13px] truncate">{media.filename || "Document"}</span>
        </a>
    );
}

function Bubble({ m }: { m: WaMessage }) {
    const time = m.at ? new Date(m.at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }) : "";
    if (m.role === "note") {
        return (
            <div className="mx-auto max-w-[85%] px-3.5 py-2 rounded-md bg-amber-50 border border-amber-200 text-sm leading-relaxed whitespace-pre-wrap">
                <span className="block text-[11px] text-amber-800 mb-0.5">Note{m.author ? ` from ${m.author}` : ""} · only your team sees this</span>
                {m.text}
            </div>
        );
    }
    const mine = m.role === "assistant";
    const who = m.sent_by === "ai" ? "Assistant" : m.sent_by === "phone" ? "From your WhatsApp app" : m.sent_by === "team" ? (m.author ?? "Your team") : null;
    return (
        <div className={cn("flex", mine ? "justify-end" : "justify-start")}>
            <div className="max-w-[78%]">
                {who && <p className="text-[11px] text-stone-500 mb-0.5 text-right">{who}</p>}
                <div className={cn("px-3.5 py-2 rounded-lg text-sm leading-relaxed whitespace-pre-wrap break-words",
                    !mine ? "bg-stone-100 text-ink rounded-bl-sm" : m.sent_by === "ai" ? "bg-plum-tint text-ink rounded-br-sm" : "bg-plum text-white rounded-br-sm")}>
                    <Media m={m} />
                    {m.text}
                </div>
                <div className={cn("flex items-center gap-1 mt-0.5 text-[11px] text-stone-400", mine ? "justify-end" : "justify-start")}>
                    <span>{time}</span>
                    {mine && <Ticks m={m} />}
                </div>
                {m.status === "failed" && (
                    <p className="flex items-start gap-1 mt-0.5 text-xs text-signal justify-end">
                        <AlertCircle size={13} className="mt-0.5 shrink-0" aria-hidden /> Not delivered. {m.error}
                    </p>
                )}
            </div>
        </div>
    );
}

function Composer({ chat, files, replies, windowLeft, onSent }: {
    chat: WaChatDetail; files: WaFile[]; replies: SavedReply[]; windowLeft: string; onSent: (m: WaMessage) => void;
}) {
    const toast = useToast();
    const [mode, setMode] = useState<"reply" | "note">("reply");
    const [input, setInput] = useState("");
    const [panel, setPanel] = useState<"replies" | "files" | null>(null);
    const [sending, setSending] = useState(false);
    const box = useRef<HTMLTextAreaElement>(null);
    const closed = !windowLeft;

    const slash = input.startsWith("/") ? input.slice(1).toLowerCase() : null;
    const matches = useMemo(() => {
        const q = slash ?? "";
        return replies.filter((r) => !q || r.title.toLowerCase().includes(q) || r.body.toLowerCase().includes(q)).slice(0, 8);
    }, [replies, slash]);
    const showReplies = mode === "reply" && (panel === "replies" || slash !== null);

    const applyReply = (r: SavedReply) => {
        const first = (chat.captured?.name || chat.profile_name || "").split(" ")[0];
        setInput(r.body.replace(/\{\{\s*name\s*\}\}/gi, first || "there"));
        setPanel(null);
        requestAnimationFrame(() => box.current?.focus());
    };

    const post = async (body: { text?: string; file_id?: string }) => {
        setSending(true);
        try {
            const path = mode === "note" && !body.file_id ? "notes" : "send";
            const m = await apiJson<WaMessage>(`/api/whatsapp/chats/${chat.id}/${path}`, { method: "POST", json: body });
            onSent(m);
            if (m.status === "failed") toast(`Not delivered. ${m.error ?? ""}`);
            return true;
        } catch (e) {
            toast((e as Error).message);
            return false;
        } finally {
            setSending(false);
        }
    };

    const send = async () => {
        const text = input.trim();
        if (!text || sending) return;
        setInput("");
        if (!(await post({ text }))) setInput(text);
    };

    return (
        <div className="relative border-t border-line">
            {showReplies && (
                <div className="absolute bottom-full left-3 right-3 mb-2 max-h-64 overflow-y-auto bg-white border border-line rounded-lg shadow-[0_12px_40px_rgba(28,23,25,0.14)] z-10">
                    {matches.length === 0 ? (
                        <p className="px-3 py-3 text-[13px] text-stone-500">{replies.length ? "No saved reply matches." : "No saved replies yet. Add them in Live chat > Settings."}</p>
                    ) : matches.map((r) => (
                        <button key={r.id} type="button" onClick={() => applyReply(r)} className="w-full text-left px-3 py-2 hover:bg-stone-50 border-t border-line first:border-t-0">
                            <span className="block text-[13px] font-medium">{r.title}</span>
                            <span className="block text-xs text-stone-500 truncate">{r.body}</span>
                        </button>
                    ))}
                </div>
            )}
            {panel === "files" && mode === "reply" && (
                <div className="absolute bottom-full left-3 right-3 mb-2 max-h-64 overflow-y-auto bg-white border border-line rounded-lg shadow-[0_12px_40px_rgba(28,23,25,0.14)] z-10">
                    {files.length === 0 ? (
                        <p className="px-3 py-3 text-[13px] text-stone-500">No files yet. Add brochures, price lists or photos in WhatsApp &gt; Files.</p>
                    ) : files.map((f) => (
                        <button key={f.id} type="button" disabled={sending}
                                onClick={async () => { setPanel(null); await post({ file_id: f.id }); }}
                                className="w-full text-left px-3 py-2 hover:bg-stone-50 border-t border-line first:border-t-0">
                            <span className="block text-[13px] font-medium">{f.name}</span>
                            <span className="block text-xs text-stone-500 truncate">{fileKind(f)} · {f.filename}</span>
                        </button>
                    ))}
                </div>
            )}
            <div className="flex flex-wrap items-center gap-2 px-3 pt-2.5">
                <Segmented label="Message type" value={mode} onChange={(v) => { setMode(v); setPanel(null); }}
                           options={[{ value: "reply", label: "Reply" }, { value: "note", label: "Internal note" }]} />
                {mode === "reply" && !closed && (
                    <>
                        <button type="button" onClick={() => setPanel(panel === "replies" ? null : "replies")} aria-expanded={panel === "replies"}
                                className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md text-[13px] text-stone-600 hover:bg-stone-100">
                            <BookmarkPlus size={13} /> Saved replies
                        </button>
                        <button type="button" onClick={() => setPanel(panel === "files" ? null : "files")} aria-expanded={panel === "files"}
                                className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md text-[13px] text-stone-600 hover:bg-stone-100">
                            <Paperclip size={13} /> Send a file
                        </button>
                    </>
                )}
                <span className="ml-auto text-xs text-stone-500">
                    {closed ? "24-hour window closed" : `You can reply for ${windowLeft}`}
                </span>
            </div>
            {mode === "reply" && closed ? (
                <p className="px-3 pb-3 pt-2 text-[13px] text-stone-600">
                    WhatsApp only lets businesses write freely within 24 hours of the customer&apos;s last message. You can reply when they write
                    again, or add an internal note.
                </p>
            ) : (
                <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex items-end gap-2 p-3">
                    <textarea
                        ref={box}
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Escape") setPanel(null);
                            if (e.key === "Enter" && !e.shiftKey) {
                                e.preventDefault();
                                if (showReplies && slash !== null && matches[0]) applyReply(matches[0]);
                                else send();
                            }
                        }}
                        placeholder={mode === "note" ? "Add a note for your team. The customer won't see it." : "Write a reply, or type / for saved replies."}
                        rows={1}
                        aria-label={mode === "note" ? "Internal note" : "Reply"}
                        className={cn("flex-1 resize-none max-h-32 border rounded-md px-3 py-2 text-sm placeholder:text-stone-400 focus:outline-none focus:ring-2",
                            mode === "note" ? "bg-amber-50 border-amber-200 focus:border-amber-400 focus:ring-amber-200/40"
                                : "bg-white border-line-strong focus:border-plum focus:ring-plum/15")}
                    />
                    <Button type="submit" variant="primary" aria-label={mode === "note" ? "Add note" : "Send"} disabled={!input.trim() || sending}><Send size={15} /></Button>
                </form>
            )}
        </div>
    );
}
