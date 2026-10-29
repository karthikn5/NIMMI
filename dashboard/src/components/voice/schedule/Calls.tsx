"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronRight, Plus, Search } from "lucide-react";
import {
    Button, Card, Dialog, EmptyState, Input, Segmented, Select, Sheet, Skeleton, Status, Textarea, useToast,
} from "@/components/ui";
import { apiSave, useApi } from "@/lib/useApi";
import { OUTCOMES } from "@/lib/voice/api";
import { ITEM_STATUS, KINDS, formatSlot, scheduleChanged, todayIn } from "@/lib/voice/schedule";
import type { ContactSummary, ScheduleItem } from "@/lib/voice/types";

const WAITING = ["queued", "review", "todo"];

/** One planned call (or to-do), with the quick action it needs. */
export function ItemRow({ item, onOpen, onChanged, showBot }: {
    item: ScheduleItem; onOpen: (id: string) => void; onChanged: () => void; showBot?: boolean;
}) {
    const toast = useToast();
    const [busy, setBusy] = useState(false);
    const quick = item.status === "review" ? { action: "approve", label: "Approve", done: "Approved" }
        : item.status === "todo" ? { action: "done", label: "Done", done: "Marked done" } : null;
    const run = async () => {
        if (!quick) return;
        setBusy(true);
        const res = await apiSave(`/api/voice/schedule/items/${item.id}/${quick.action}`, "POST");
        setBusy(false);
        if (!res.ok) return toast(res.message);
        toast(quick.done);
        onChanged();
        scheduleChanged();
    };

    return (
        <li className="relative grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[9.5rem_minmax(0,1fr)_9rem_6rem] items-center gap-x-4 gap-y-1 px-5 py-3 border-t border-line first:border-t-0 hover:bg-stone-50 transition-colors">
            <span className="hidden sm:block text-[13px] tabular-nums">{item.status === "todo" ? "As soon as you can" : formatSlot(item.local, item.timezone)}</span>
            <div className="min-w-0">
                <button type="button" onClick={() => onOpen(item.id)}
                        className="text-sm font-medium text-left truncate max-w-full after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-plum focus-visible:after:-outline-offset-2">
                    {item.name || item.number}
                </button>
                <p className="text-xs text-stone-500 truncate mt-0.5">
                    <span className="sm:hidden tabular-nums">{item.status === "todo" ? "" : `${formatSlot(item.local, item.timezone)} · `}</span>
                    {[KINDS[item.kind].short, item.purpose, showBot && item.bot_name].filter(Boolean).join(" · ")}
                </p>
            </div>
            <Status tone={ITEM_STATUS[item.status].tone}>{ITEM_STATUS[item.status].label}</Status>
            <div className="hidden sm:flex justify-end relative">
                {quick ? <Button size="sm" onClick={run} disabled={busy}>{quick.label}</Button>
                    : <ChevronRight size={16} className="text-stone-300" aria-hidden />}
            </div>
        </li>
    );
}

type KindFilter = "" | "callback" | "follow_up" | "meeting" | "person";

export function CallsPanel({ botId, showBot, openId, onOpen }: {
    botId: string; showBot: boolean; openId: string | null; onOpen: (id: string | null) => void;
}) {
    const [kind, setKind] = useState<KindFilter>("");
    const [status, setStatus] = useState<"open" | "done">("open");
    const [adding, setAdding] = useState(false);
    const list = useApi<ScheduleItem[]>(`/api/voice/schedule/items?kind=${kind}&status=${status}&bot_id=${encodeURIComponent(botId)}`);

    return (
        <>
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                <div className="flex flex-wrap items-center gap-2">
                    <Segmented label="Show" value={status} onChange={setStatus} options={[{ value: "open", label: "Coming up" }, { value: "done", label: "Finished" }]} />
                    <Select aria-label="Kind of call" className="w-auto" value={kind} onChange={(e) => setKind(e.target.value as KindFilter)}>
                        <option value="">All kinds</option>
                        <option value="callback">Call-backs</option>
                        <option value="follow_up">Follow-ups</option>
                        <option value="meeting">Meeting calls</option>
                        <option value="person">For the team</option>
                    </Select>
                </div>
                <Button size="sm" onClick={() => setAdding(true)}><Plus size={14} aria-hidden /> Schedule a call</Button>
            </div>
            <Card>
                {list.loading ? (
                    <div className="p-5 space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-11" />)}</div>
                ) : list.error ? (
                    <p className="p-5 text-sm text-signal">Couldn&apos;t load calls. {list.error}</p>
                ) : !list.data?.length ? (
                    <EmptyState
                        title={status === "open" ? "Nothing planned" : "Nothing finished yet"}
                        body={status === "open"
                            ? "Call-backs callers ask for, follow-ups after calls and calls about meetings show here before they're made."
                            : "Calls move here once they've been made, or called off."}
                    />
                ) : (
                    <ul>{list.data.map((item) => <ItemRow key={item.id} item={item} onOpen={onOpen} onChanged={list.reload} showBot={showBot} />)}</ul>
                )}
            </Card>
            <CallSheet id={openId} items={list.data ?? []} onClose={() => onOpen(null)} onChanged={list.reload} />
            <NewCallDialog open={adding} botId={botId} onClose={() => setAdding(false)} onMade={() => { setAdding(false); list.reload(); }} />
        </>
    );
}

export function CallSheet({ id, items, onClose, onChanged }: { id: string | null; items: ScheduleItem[]; onClose: () => void; onChanged: () => void }) {
    const toast = useToast();
    const [item, setItem] = useState<ScheduleItem | null>(null);
    const [form, setForm] = useState({ date: "", time: "", about: "" });
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        const found = items.find((i) => i.id === id) ?? null;
        setItem(found);
        if (found) setForm({ date: found.local?.slice(0, 10) ?? "", time: found.local?.slice(11, 16) ?? "", about: found.purpose });
    }, [id, items]);

    const act = async (path: string, method: "POST" | "PATCH", body: unknown, done: string) => {
        if (!item) return;
        setBusy(true);
        const res = await apiSave(`/api/voice/schedule/items/${item.id}${path}`, method, body);
        setBusy(false);
        if (!res.ok) return toast(res.message);
        setItem(res.data as ScheduleItem);
        toast(done);
        onChanged();
        scheduleChanged();
    };

    const waiting = item && WAITING.includes(item.status);
    const edited = item && (form.about !== item.purpose || `${form.date}T${form.time}` !== item.local);

    return (
        <Sheet open={!!id && !!item} onClose={onClose} title={item ? (item.name || item.number) : ""}
               subtitle={item ? `${KINDS[item.kind].label} · ${item.bot_name}` : undefined}>
            {item && (
                <div className="px-6 py-5 space-y-6">
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                        <Status tone={ITEM_STATUS[item.status].tone}>{ITEM_STATUS[item.status].label}</Status>
                        <a href={`tel:${item.number.replace(/\s/g, "")}`} className="text-[13px] text-plum hover:underline underline-offset-4 tabular-nums">{item.number}</a>
                        {item.status !== "todo" && <span className="text-[13px] text-stone-600">{formatSlot(item.local, item.timezone)}</span>}
                    </div>

                    {waiting && (
                        <div className="flex flex-wrap gap-2">
                            {item.status === "review" && <Button size="sm" variant="primary" disabled={busy} onClick={() => act("/approve", "POST", undefined, "Approved")}>Approve</Button>}
                            {item.status !== "todo" && <Button size="sm" disabled={busy} onClick={() => act("/now", "POST", undefined, "It'll be called as soon as calling hours allow")}>Call now</Button>}
                            {item.status === "todo" && <Button size="sm" variant="primary" disabled={busy} onClick={() => act("/done", "POST", undefined, "Marked done")}>I called them</Button>}
                            <Button size="sm" variant="ghost" disabled={busy} onClick={() => act("/cancel", "POST", undefined, "Called off")}>Call it off</Button>
                        </div>
                    )}

                    {item.kind === "person" ? (
                        <section>
                            <h3 className="text-sm font-medium">They asked for a person to call them</h3>
                            <p className="text-[13px] text-stone-700 mt-1.5 leading-relaxed">{item.purpose}</p>
                        </section>
                    ) : waiting ? (
                        <section className="space-y-3">
                            {(item.kind === "meeting" || item.kind === "no_show") && (
                                <p className="text-[13px] text-stone-700 leading-relaxed">
                                    {item.purpose}. <span className="text-stone-500">What the assistant says comes from the meeting as it is when it calls.</span>
                                </p>
                            )}
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label htmlFor="i-day" className="text-[13px] text-stone-600">Day</label>
                                    <Input id="i-day" type="date" className="mt-1" min={todayIn(item.timezone)} value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
                                </div>
                                <div>
                                    <label htmlFor="i-time" className="text-[13px] text-stone-600">Time</label>
                                    <Input id="i-time" type="time" className="mt-1 tabular-nums" value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} />
                                </div>
                            </div>
                            {item.kind !== "meeting" && item.kind !== "no_show" && (
                                <div>
                                    <label htmlFor="i-about" className="text-[13px] text-stone-600">{item.kind === "follow_up" ? "What the assistant will do on this call" : "What it's about"}</label>
                                    <Textarea id="i-about" className="mt-1" rows={3} maxLength={600} value={form.about} onChange={(e) => setForm({ ...form, about: e.target.value })} />
                                    {item.kind === "follow_up" && <p className="text-xs text-stone-500 mt-1">Written by the assistant from their last call. Change it if you know better.</p>}
                                </div>
                            )}
                            <div className="flex justify-end">
                                <Button size="sm" variant="primary" disabled={busy || !edited}
                                        onClick={() => act("", "PATCH", { date: form.date, time: form.time, about: form.about }, "Saved")}>Save</Button>
                            </div>
                        </section>
                    ) : item.purpose ? (
                        <section>
                            <h3 className="text-sm font-medium">What it was about</h3>
                            <p className="text-[13px] text-stone-700 mt-1.5 leading-relaxed">{item.purpose}</p>
                        </section>
                    ) : null}

                    {item.result && (
                        <section>
                            <h3 className="text-sm font-medium">How the call went</h3>
                            <div className="mt-1.5 text-[13px]">
                                <Status tone={OUTCOMES[item.result.outcome]?.tone ?? "neutral"}>{OUTCOMES[item.result.outcome]?.label ?? item.result.outcome}</Status>
                                {item.result.summary && <p className="text-stone-700 mt-1 leading-relaxed">{item.result.summary}</p>}
                                {item.call_id && <Link href={`/dashboard/voice/calls?call=${item.call_id}`} className="inline-block mt-1 text-plum hover:underline underline-offset-4">Open the call</Link>}
                            </div>
                        </section>
                    )}

                    <dl className="grid grid-cols-[minmax(0,8.5rem)_1fr] gap-x-4 gap-y-2.5 text-[13px] border-t border-line pt-5">
                        <dt className="text-stone-500">Why we may call</dt>
                        <dd className="text-stone-700">{item.consent}</dd>
                        {item.attempts > 0 && (<><dt className="text-stone-500">Tries</dt><dd>{item.attempts}</dd></>)}
                        {item.last_error && (<><dt className="text-stone-500">Last note</dt><dd className="text-stone-700">{item.last_error}</dd></>)}
                        {item.source_call_id && (
                            <>
                                <dt className="text-stone-500">Arranged on</dt>
                                <dd><Link href={`/dashboard/voice/calls?call=${item.source_call_id}`} className="text-plum hover:underline underline-offset-4">Their call</Link></dd>
                            </>
                        )}
                        <dt className="text-stone-500">Arranged by</dt>
                        <dd>{item.from === "team" ? "Your team" : item.from === "website" ? "Them, in your website chat" : "The assistant"}</dd>
                    </dl>
                </div>
            )}
        </Sheet>
    );
}

/** The team asks the assistant to call someone it has spoken with. */
export function NewCallDialog({ open, botId, onClose, onMade, contact: fixed }: {
    open: boolean; botId: string; onClose: () => void; onMade: () => void; contact?: { id: string; label: string };
}) {
    const toast = useToast();
    const [typed, setTyped] = useState("");
    const [q, setQ] = useState("");
    const [picked, setPicked] = useState<{ id: string; label: string } | null>(null);
    const [form, setForm] = useState({ date: "", time: "11:00", about: "" });
    const [busy, setBusy] = useState(false);
    const contacts = useApi<ContactSummary[]>(open && !fixed ? `/api/voice/contacts?bot_id=${encodeURIComponent(botId)}&q=${encodeURIComponent(q)}` : null);

    const fixedId = fixed?.id, fixedLabel = fixed?.label;
    useEffect(() => {
        if (!open) return;
        setTyped(""); setQ(""); setPicked(fixedId ? { id: fixedId, label: fixedLabel ?? "" } : null);
        setForm({ date: todayIn("Asia/Kolkata", 1), time: "11:00", about: "" });
    }, [open, fixedId, fixedLabel]);
    useEffect(() => { const t = setTimeout(() => setQ(typed.trim()), 300); return () => clearTimeout(t); }, [typed]);

    const make = async () => {
        if (!picked) return;
        setBusy(true);
        const res = await apiSave("/api/voice/schedule/items", "POST", { contact_id: picked.id, ...form });
        setBusy(false);
        if (!res.ok) return toast(res.message);
        toast("Scheduled. The assistant will call them then.");
        onMade();
    };

    return (
        <Dialog open={open} onClose={onClose} title="Schedule a call"
                description="The assistant calls someone it has spoken with before, at the time you choose, about what you write here."
                footer={<>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" disabled={busy || !picked || !form.date || !form.time} onClick={make}>{busy ? "Scheduling…" : "Schedule"}</Button>
                </>}>
            <div className="space-y-4">
                {fixed ? (
                    <p className="text-sm">Calling <span className="font-medium">{fixed.label}</span></p>
                ) : picked ? (
                    <div className="flex items-center justify-between gap-3 text-sm">
                        <span>Calling <span className="font-medium">{picked.label}</span></span>
                        <Button size="sm" variant="ghost" onClick={() => setPicked(null)}>Change</Button>
                    </div>
                ) : (
                    <div>
                        <label htmlFor="n-who" className="text-[13px] text-stone-600">Who</label>
                        <div className="relative mt-1">
                            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-stone-400" aria-hidden />
                            <Input id="n-who" className="pl-8" placeholder="Name or number" value={typed} onChange={(e) => setTyped(e.target.value)} />
                        </div>
                        <ul className="mt-2 max-h-44 overflow-y-auto border border-line rounded-md">
                            {contacts.loading ? <li className="p-3"><Skeleton className="h-6" /></li>
                                : !contacts.data?.length ? <li className="px-3 py-2.5 text-[13px] text-stone-500">No one matches. Only people the assistant has spoken with can be called.</li>
                                : contacts.data.slice(0, 30).map((c) => (
                                    <li key={c.id}>
                                        <button type="button" onClick={() => setPicked({ id: c.id, label: c.name || c.number })}
                                                className="w-full flex justify-between gap-3 px-3 py-2 text-left text-[13px] border-t border-line first:border-t-0 hover:bg-stone-50 focus-visible:outline-2 focus-visible:outline-plum focus-visible:-outline-offset-2">
                                            <span className="truncate">{c.name || "Name not given"}</span>
                                            <span className="text-stone-500 tabular-nums shrink-0">{c.number}</span>
                                        </button>
                                    </li>
                                ))}
                        </ul>
                    </div>
                )}
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label htmlFor="n-day" className="text-[13px] text-stone-600">Day</label>
                        <Input id="n-day" type="date" className="mt-1" min={todayIn("Asia/Kolkata")} value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
                    </div>
                    <div>
                        <label htmlFor="n-time" className="text-[13px] text-stone-600">Time</label>
                        <Input id="n-time" type="time" className="mt-1 tabular-nums" value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} />
                    </div>
                </div>
                <div>
                    <label htmlFor="n-about" className="text-[13px] text-stone-600">What the call is about</label>
                    <Textarea id="n-about" className="mt-1" rows={3} maxLength={300} value={form.about} placeholder="e.g. Tell them the new weekend batch starts on 15 November, and ask if they'd like a seat."
                              onChange={(e) => setForm({ ...form, about: e.target.value })} />
                </div>
            </div>
        </Dialog>
    );
}
