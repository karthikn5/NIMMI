"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Paperclip, Sparkles } from "lucide-react";
import { Button, Card, EmptyState, Input, Notice, Select, Skeleton, Status, Textarea, cn, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { DRAFTS_CHANGED, KIND_LABEL, type MailConnections, type Thread, type ThreadMessageRow, type ThreadRow, type Threads, type ThreadStatus } from "@/lib/email";
import { useApi } from "@/lib/useApi";
import { formatWhen } from "@/lib/voice/api";

const TABS: { value: ThreadStatus; label: string }[] = [{ value: "open", label: "Waiting" }, { value: "answered", label: "Answered" }, { value: "closed", label: "Closed" }];
const WHO: Record<ThreadMessageRow["who"], string> = { customer: "", team: "Your team", ai: "The AI", nimmi: "Automatic email" };

function ThreadList({ threads, active, onOpen }: { threads: ThreadRow[]; active: string | null; onOpen: (id: string) => void }) {
    return (
        <ul>
            {threads.map((t) => (
                <li key={t.id} className="border-t border-line first:border-t-0">
                    <button type="button" onClick={() => onOpen(t.id)} aria-current={active === t.id ? "true" : undefined}
                            className={cn("w-full px-4 py-3 text-left hover:bg-paper/70 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-plum", active === t.id && "bg-plum-tint/40")}>
                        <span className="flex items-baseline gap-2">
                            <span className={cn("flex-1 min-w-0 text-sm truncate", t.unread > 0 && "font-semibold")}>{t.name || t.email}</span>
                            {t.last_at && <span className="text-xs text-stone-500 whitespace-nowrap">{formatWhen(t.last_at)}</span>}
                        </span>
                        <span className="block text-[13px] text-stone-600 truncate mt-0.5">{t.last || t.subject}</span>
                        <span className="flex flex-wrap gap-x-3 mt-1 text-xs text-stone-500">
                            {t.kind && <span>{KIND_LABEL[t.kind]}</span>}
                            {t.draft && <span className="text-plum">Draft ready</span>}
                            {t.bot_name && <span className="truncate">{t.bot_name}</span>}
                        </span>
                    </button>
                </li>
            ))}
        </ul>
    );
}

function Message({ m, threadId }: { m: ThreadMessageRow; threadId: string }) {
    const toast = useToast();
    const theirs = m.direction === "in";
    const openAttachment = async (id: string) => {
        try {  // A fresh link each time: Resend's last an hour.
            const { url } = await apiJson<{ url: string }>(`/api/email/inbox/${threadId}/attachments/${m.id}/${id}`);
            window.open(url, "_blank", "noopener");
        } catch (e) {
            toast((e as Error).message);
        }
    };
    return (
        <li className={cn("rounded-md border border-line p-3.5", theirs ? "bg-white" : "bg-paper/60")}>
            <p className="flex flex-wrap items-baseline gap-x-2 text-xs text-stone-500">
                <span className="font-medium text-stone-700">{theirs ? m.sender : WHO[m.who]}</span>
                {m.created_at && <span>{formatWhen(m.created_at)}</span>}
                {theirs && m.kind && <span>· {KIND_LABEL[m.kind]}</span>}
            </p>
            {/* An email is shown as text, never as HTML: it comes from outside. */}
            <p className="text-[13.5px] leading-relaxed whitespace-pre-wrap break-words mt-1.5">{m.text}</p>
            {m.attachments.length > 0 && (
                <ul className="flex flex-wrap gap-2 mt-2">
                    {m.attachments.map((a) => (
                        <li key={a.id}>
                            <button type="button" onClick={() => openAttachment(a.id)} className="inline-flex items-center gap-1 text-[13px] text-plum hover:underline focus-visible:outline-2 focus-visible:outline-plum rounded">
                                <Paperclip size={12} aria-hidden /> {a.filename}
                            </button>
                        </li>
                    ))}
                </ul>
            )}
            {m.note && <p className="text-xs text-stone-500 mt-2">{m.note}</p>}
        </li>
    );
}

function Conversation({ id, onBack, onChanged }: { id: string; onBack: () => void; onChanged: () => void }) {
    const toast = useToast();
    const thread = useApi<Thread>(`/api/email/inbox/${id}`);
    const connections = useApi<MailConnections>("/api/email/connections");
    const mine = connections.data?.items.find((c) => c.mine && c.can_send && c.status === "connected")?.address;
    const [text, setText] = useState("");
    const [draftText, setDraftText] = useState("");
    const [notes, setNotes] = useState("");
    const [busy, setBusy] = useState(false);
    const [waiting, setWaiting] = useState(false);
    const t = thread.data;
    const draft = useMemo(() => t?.messages.find((m) => m.status === "draft") ?? null, [t]);
    const { reload } = thread;
    const loaded = t?.id;

    useEffect(() => { if (loaded) onChanged(); }, [loaded, onChanged]);  // opening it marked it read: the counts follow
    useEffect(() => { setDraftText(draft?.text ?? ""); }, [draft?.id, draft?.text]);
    useEffect(() => { setNotes(t?.notes ?? ""); setText(""); }, [t?.id]);  // eslint-disable-line react-hooks/exhaustive-deps

    // Write with AI: its draft comes in by itself, in a few seconds.
    useEffect(() => {
        if (!waiting) return;
        if (draft) { setWaiting(false); return; }
        const tick = setInterval(() => { void reload(); }, 3000);
        const stop = setTimeout(() => { setWaiting(false); toast("The AI didn't write an answer. Try again, or write it yourself."); }, 90_000);
        return () => { clearInterval(tick); clearTimeout(stop); };
    }, [waiting, draft, reload, toast]);

    const act = async (run: () => Promise<unknown>, done?: string) => {
        setBusy(true);
        try {
            await run();
            await reload();
            onChanged();
            if (done) toast(done);
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    if (thread.error) return <p className="p-5 text-sm text-signal">{thread.error}</p>;
    if (!t) return <div className="p-5"><Skeleton className="h-64" /></div>;
    const url = `/api/email/inbox/${t.id}`;
    const shown = t.messages.filter((m) => m.status !== "draft");
    return (
        <div>
            <header className="flex flex-wrap items-center gap-3 px-5 py-3.5 border-b border-line">
                <button type="button" onClick={onBack} aria-label="Back to the list" className="lg:hidden p-1 rounded text-stone-500 hover:text-ink focus-visible:outline-2 focus-visible:outline-plum"><ArrowLeft size={16} /></button>
                <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-medium truncate">{t.name || t.email}</h3>
                    <p className="text-[13px] text-stone-500 truncate">{t.name ? `${t.email} · ` : ""}{t.subject}</p>
                </div>
                <Select aria-label="Status" className="w-36" value={t.status === "quiet" ? "open" : t.status} disabled={busy}
                        onChange={(e) => act(() => apiJson(url, { method: "PUT", json: { status: e.target.value } }))}>
                    {TABS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                </Select>
            </header>
            <div className="p-5 space-y-3">
                {t.contact && (
                    <p className="text-[13px] text-stone-600">
                        {[t.contact.name, t.contact.phone, t.contact.lead_status && `Lead: ${t.contact.lead_status}`].filter(Boolean).join(" · ")}
                        {t.calls.length > 0 && <> · <Link href={`/dashboard/voice/calls?call=${t.calls[0].id}`} className="text-plum hover:underline">Last call</Link></>}
                    </p>
                )}
                <ol className="space-y-2.5" aria-label="The emails, oldest first">
                    {shown.map((m) => <Message key={m.id} m={m} threadId={t.id} />)}
                </ol>
                {draft ? (
                    <section aria-label="The AI's draft" className="rounded-md border border-plum/30 p-3.5">
                        <p className="text-xs font-medium text-plum">The AI&apos;s draft</p>
                        {draft.note && <Notice title="Read this one before it goes" className="mt-2 mb-2">{draft.note}</Notice>}
                        {draft.action && <p className="text-[13px] text-stone-600 mt-1">Sending it also books the {draft.action.type === "callback" ? "call-back" : "meeting"}.</p>}
                        <Textarea aria-label="Draft answer" rows={5} className="mt-2" maxLength={10000} value={draftText} onChange={(e) => setDraftText(e.target.value)} />
                        <div className="flex flex-wrap justify-end gap-2 mt-2">
                            <Button variant="ghost" disabled={busy} onClick={() => act(() => apiJson(`${url}/drafts/${draft.id}`, { method: "DELETE" }), "Draft dropped")}>Drop it</Button>
                            <Button variant="primary" disabled={busy || !draftText.trim()} onClick={() => act(() => apiJson(`${url}/drafts/${draft.id}/send`, { method: "POST", json: { text: draftText } }), "Sent")}>Send</Button>
                        </div>
                    </section>
                ) : (
                    <section aria-label="Your answer">
                        <Textarea aria-label="Your answer" rows={4} maxLength={10000} placeholder="Write your answer" value={text} onChange={(e) => setText(e.target.value)} />
                        {mine && <p className="text-xs text-stone-500 mt-1">It goes from {mine}.</p>}
                        <div className="flex flex-wrap justify-end gap-2 mt-2">
                            {t.bot_id && (
                                <Button variant="ghost" disabled={busy || waiting} onClick={() => act(async () => { await apiJson(`${url}/write`, { method: "POST" }); setWaiting(true); })}>
                                    <Sparkles size={13} aria-hidden /> {waiting ? "Writing…" : "Write with AI"}
                                </Button>
                            )}
                            <Button variant="primary" disabled={busy || !text.trim()} onClick={() => act(async () => { await apiJson(`${url}/reply`, { method: "POST", json: { text } }); setText(""); }, "Sent")}>Send</Button>
                        </div>
                    </section>
                )}
                <label className="block pt-1">
                    <span className="text-xs text-stone-500">Your team&apos;s notes. The customer never sees these.</span>
                    <Textarea className="mt-1" rows={2} maxLength={4000} value={notes} onChange={(e) => setNotes(e.target.value)}
                              onBlur={() => { if (notes !== t.notes) void act(() => apiJson(url, { method: "PUT", json: { notes } }), "Saved"); }} />
                </label>
            </div>
        </div>
    );
}

function Inbox() {
    const router = useRouter();
    const params = useSearchParams();
    const active = params.get("thread");
    const [tab, setTab] = useState<ThreadStatus>("open");
    const [q, setQ] = useState("");
    const list = useApi<Threads>(`/api/email/inbox?status=${tab}&q=${encodeURIComponent(q)}`);
    const { reload } = list;

    useEffect(() => {
        const tick = setInterval(() => { if (document.visibilityState === "visible") void reload(); }, 20_000);
        return () => clearInterval(tick);
    }, [reload]);

    const open = useCallback((id: string | null) => router.replace(id ? `/dashboard/email/inbox?thread=${id}` : "/dashboard/email/inbox", { scroll: false }), [router]);
    const changed = useCallback(() => { void reload(); window.dispatchEvent(new Event(DRAFTS_CHANGED)); }, [reload]);

    if (list.error) return <p className="text-sm text-signal">{list.error}</p>;
    const data = list.data;
    return (
        <>
            {data && !data.enabled && (
                <Notice title="Replies aren't coming to Nimmi yet">
                    Until this is switched on for your account, replies go straight to your own mailbox and nothing shows here.
                </Notice>
            )}
            <Card className="lg:grid lg:grid-cols-[22rem_minmax(0,1fr)] overflow-hidden">
                <section aria-label="Conversations" className={cn("lg:border-r border-line", active && "hidden lg:block")}>
                    <div className="px-4 pt-3.5 pb-3 border-b border-line space-y-2.5">
                        <div role="group" aria-label="Show" className="flex gap-4">
                            {TABS.map((s) => (
                                <button key={s.value} type="button" aria-pressed={tab === s.value} onClick={() => setTab(s.value)}
                                        className={cn("text-[13px] focus-visible:outline-2 focus-visible:outline-plum rounded", tab === s.value ? "text-ink font-medium" : "text-stone-500 hover:text-ink")}>
                                    {s.label}{data ? ` ${data.counts[s.value]}` : ""}
                                </button>
                            ))}
                        </div>
                        <Input aria-label="Search" placeholder="Search name, email or subject" value={q} onChange={(e) => setQ(e.target.value)} />
                    </div>
                    {!data ? <div className="p-4"><Skeleton className="h-40" /></div> : data.items.length === 0 ? (
                        <EmptyState title="Nothing here" body={tab === "open" ? "When someone replies to one of your emails, it shows here." : "Conversations you've moved here show up here."} />
                    ) : <ThreadList threads={data.items} active={active} onOpen={open} />}
                </section>
                <section aria-label="The conversation" className={cn("min-w-0", !active && "hidden lg:block")}>
                    {active ? <Conversation key={active} id={active} onBack={() => open(null)} onChanged={changed} /> : (
                        <div className="py-24 px-6 text-center"><Status tone="neutral">Pick a conversation</Status></div>
                    )}
                </section>
            </Card>
        </>
    );
}

export default function Page() {
    return <Suspense fallback={<Skeleton className="h-96" />}><Inbox /></Suspense>;
}
