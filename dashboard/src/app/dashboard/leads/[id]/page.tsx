"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { ArrowLeft, Mail, MessageCircle, Phone } from "lucide-react";
import { Button, Card, Dialog, Input, PhraseInput, Select, Skeleton, Status, Textarea, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { CHANNEL, KIND, ORIGIN, REACH_LABEL, STAGES, dueInline, formatDue, inline, localInput, rupees, sourceLabel, type LeadDetail, type LeadTask, type ReachChannel, type TimelineItem } from "@/lib/leads";
import { useApi } from "@/lib/useApi";
import { formatWhen } from "@/lib/voice/api";
import { Promises } from "@/components/leads/Promises";

const WHAT: Record<string, string> = {
    came_in: "Came in", asked_again: "Asked again", assigned: "Looked after by", stage: "Stage", note: "Note", result: "Tried them", won: "Won", lost: "Lost", reopened: "Reopened",
    submission: "Form", call: "Call", meeting: "Meeting", email: "Email sent", reply: "They replied", task: "Done", chat: "Chat", imported: "Imported", real: "Not junk",
    junk: "Marked as junk", permission: "Contact preference", stopped: "Automatic steps stopped", whatsapp: "WhatsApp",
    promise: "Promised", promise_kept: "Promise kept", promise_cancel: "Promise cancelled",
};

function Step({ item }: { item: TimelineItem }) {
    const found = Object.entries(item.found ?? {});
    const link = item.kind === "call" && item.call_id ? `/dashboard/voice/calls?call=${item.call_id}` : item.kind === "meeting" && item.meeting_id ? `/dashboard/voice/schedule?tab=meetings&meeting=${item.meeting_id}`
        : item.kind === "reply" && item.thread_id ? `/dashboard/email/inbox?thread=${item.thread_id}` : item.kind === "chat" ? item.chat_link ?? null : null;
    return (
        <li className="px-5 py-3 border-t border-line first:border-t-0">
            <div className="flex items-baseline justify-between gap-3">
                <span className="text-[13px] font-medium">{WHAT[item.kind] ?? item.kind}{item.who ? <span className="text-stone-500 font-normal"> · {item.who}</span> : null}</span>
                <span className="text-xs text-stone-500 whitespace-nowrap">{formatWhen(item.at)}</span>
            </div>
            <p className="text-[13px] text-stone-700 mt-0.5 break-words">{item.text}{link && <> <Link href={link} className="text-plum hover:underline">Open</Link></>}</p>
            {!!found.length && (
                <dl className="mt-1 text-[13px] text-stone-600">
                    {found.map(([k, v]) => <div key={k} className="flex gap-2"><dt className="text-stone-500 capitalize">{k}:</dt><dd className="break-words">{String(v)}</dd></div>)}
                </dl>
            )}
            {!!item.consents?.length && item.consents.map((c, i) => <p key={i} className="text-xs text-stone-500 mt-1">{c.agreed ? "Ticked" : "Not ticked"}: {c.text}</p>)}
        </li>
    );
}

function TaskRow({ task, onChanged }: { task: LeadTask; onChanged: () => void }) {
    const toast = useToast();
    const [busy, setBusy] = useState(false);
    const finish = async (status: "done" | "cancelled") => {
        setBusy(true);
        try {
            await apiJson(`/api/crm/tasks/${task.id}`, { method: "PUT", json: { status } });
            onChanged();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    const late = new Date(task.due_at).getTime() < Date.now();
    return (
        <li className="flex flex-wrap items-center gap-2 px-5 py-3 border-t border-line first:border-t-0">
            <span className="flex-1 min-w-44">
                <span className="block text-sm">{task.title}</span>
                <span className="block text-[13px] text-stone-500">{[KIND[task.kind], formatDue(task.due_at), task.owner].filter(Boolean).join(" · ")}</span>
            </span>
            {late && <Status tone="bad">Overdue</Status>}
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => finish("cancelled")}>Drop</Button>
            <Button size="sm" disabled={busy} onClick={() => finish("done")}>Done</Button>
        </li>
    );
}

function NewTask({ lead, onDone }: { lead: LeadDetail; onDone: () => void }) {
    const toast = useToast();
    const [title, setTitle] = useState("");
    const [kind, setKind] = useState(lead.e164 ? "call" : "email");
    const [when, setWhen] = useState(() => localInput(new Date(Date.now() + 3_600_000)));
    const [busy, setBusy] = useState(false);
    const add = async () => {
        setBusy(true);
        try {
            await apiJson(`/api/crm/leads/${lead.id}/tasks`, { method: "POST", json: { title, kind, due_at: new Date(when).toISOString() } });
            setTitle("");
            onDone();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    return (
        <form className="flex flex-wrap gap-2 px-5 py-4 border-t border-line" onSubmit={(e) => { e.preventDefault(); void add(); }}>
            <Input aria-label="Next step" className="flex-1 min-w-48" placeholder="What's the next step?" maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
            <Select aria-label="Kind of step" className="w-32" value={kind} onChange={(e) => setKind(e.target.value)}>
                {lead.kinds.map((k) => <option key={k} value={k}>{KIND[k] ?? k}</option>)}
            </Select>
            <Input aria-label="When" type="datetime-local" className="w-56" value={when} onChange={(e) => setWhen(e.target.value)} />
            <Button type="submit" disabled={busy || !title.trim() || !when}>Add</Button>
        </form>
    );
}

function HowItWent({ lead, onDone }: { lead: LeadDetail; onDone: () => void }) {
    const toast = useToast();
    const [later, setLater] = useState(false);
    const [when, setWhen] = useState(() => localInput(new Date(Date.now() + 86_400_000)));
    const [busy, setBusy] = useState(false);
    const say = async (result: string, next_at?: string) => {
        setBusy(true);
        try {
            await apiJson(`/api/crm/leads/${lead.id}/result`, { method: "POST", json: { result, next_at } });
            setLater(false);
            onDone();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    return (
        <div className="px-5 py-4 border-t border-line">
            <p className="text-[13px] text-stone-500 mb-2">How did it go?</p>
            <div className="flex flex-wrap gap-2">
                {Object.entries(lead.results).map(([key, label]) => (
                    <Button key={key} size="sm" disabled={busy} onClick={() => (key === "later" ? setLater(!later) : say(key))}>{label}</Button>
                ))}
            </div>
            {later && (
                <div className="flex flex-wrap gap-2 mt-2">
                    <Input aria-label="Call them on" type="datetime-local" className="w-56" value={when} onChange={(e) => setWhen(e.target.value)} />
                    <Button size="sm" variant="primary" disabled={busy || !when} onClick={() => say("later", new Date(when).toISOString())}>Set the call</Button>
                </div>
            )}
        </div>
    );
}

/** What may reach them by itself, and why not: the same check every automatic channel makes before it sends (phase 4). The team writes down what they said. */
function CanReach({ lead, onDone }: { lead: LeadDetail; onDone: () => void }) {
    const toast = useToast();
    const [open, setOpen] = useState(false);
    const [channel, setChannel] = useState<ReachChannel>("call");
    const [state, setState] = useState<"granted" | "refused">("granted");
    const [words, setWords] = useState("");
    const [busy, setBusy] = useState(false);
    if (!lead.reach) return null;
    const reach = lead.reach;
    const save = async () => {
        setBusy(true);
        try {
            await apiJson(`/api/crm/leads/${lead.id}/permissions`, { method: "POST", json: { channel, state, words } });
            setOpen(false);
            setWords("");
            onDone();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    const said = (ch: ReachChannel) => (lead.permissions ?? []).find((p) => p.channel === ch && p.purpose === "service");
    return (
        <Card>
            <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4 pb-3">
                <div className="min-w-0 flex-1">
                    <h3 className="text-sm font-medium">What can reach them by itself</h3>
                    <p className="text-[13px] text-stone-500 mt-0.5">Checked again just before anything automatic goes. You can always contact them yourself.</p>
                </div>
                <Button size="sm" onClick={() => setOpen(true)} data-agent="lead.permission">Record what they said</Button>
            </div>
            <ul className="border-t border-line">
                {(Object.keys(REACH_LABEL) as ReachChannel[]).map((ch) => {
                    const r = reach[ch];
                    if (!r) return null;
                    const p = said(ch);
                    return (
                        <li key={ch} className="flex flex-wrap items-start gap-x-3 gap-y-1 px-5 py-3 border-t border-line first:border-t-0">
                            <span className="w-44 shrink-0 text-[13px]">{REACH_LABEL[ch]}</span>
                            <span className="w-24 shrink-0"><Status tone={r.ok ? "good" : r.code === "hours" ? "warn" : "neutral"}>{r.ok ? "Allowed" : r.code === "hours" ? "Later" : "Not now"}</Status></span>
                            <span className="flex-1 min-w-48 text-[13px] text-stone-600">
                                {r.ok ? r.cause : r.reason}{r.wait_until ? `. From ${dueInline(r.wait_until)}` : ""}{!r.ok && r.code === "hours" && r.cause ? `. ${r.cause}` : ""}
                                {p && <span className="block text-xs text-stone-500 mt-0.5">{p.state === "granted" ? "Said yes" : "Said no"}{p.words ? `: ${p.words}` : ""}{p.given_at ? ` · ${formatWhen(p.given_at)}` : ""}</span>}
                            </span>
                        </li>
                    );
                })}
            </ul>
            <Dialog open={open} onClose={() => setOpen(false)} title="What they said" description="Kept with your name. A no they gave themselves can only be changed by them."
                    footer={<>
                        <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
                        <Button variant="primary" disabled={busy || (state === "granted" && !words.trim())} onClick={save}>Save</Button>
                    </>}>
                <div className="space-y-3">
                    <label className="block">
                        <span className="text-xs text-stone-500">About</span>
                        <Select aria-label="About" className="mt-1" value={channel} onChange={(e) => setChannel(e.target.value as ReachChannel)}>
                            {(Object.keys(REACH_LABEL) as ReachChannel[]).map((ch) => <option key={ch} value={ch}>{REACH_LABEL[ch]}</option>)}
                        </Select>
                    </label>
                    <label className="block">
                        <span className="text-xs text-stone-500">They said</span>
                        <Select aria-label="They said" className="mt-1" value={state} onChange={(e) => setState(e.target.value as "granted" | "refused")}>
                            <option value="granted">Yes</option>
                            <option value="refused">No, don&apos;t contact me this way</option>
                        </Select>
                    </label>
                    <label className="block">
                        <span className="text-xs text-stone-500">How and when{state === "granted" ? "" : " (optional)"}</span>
                        <Input aria-label="How and when" className="mt-1" maxLength={300} placeholder="Said yes on the phone on 3 Nov" value={words} onChange={(e) => setWords(e.target.value)} />
                    </label>
                    {channel === "call" && state === "granted" && <p className="text-xs text-stone-500">A yes to calls lasts 7 days, as TRAI&apos;s rules say. They can give it again.</p>}
                </div>
            </Dialog>
        </Card>
    );
}

function Close({ lead, open, onClose, onDone }: { lead: LeadDetail; open: "won" | "lost" | null; onClose: () => void; onDone: () => void }) {
    const toast = useToast();
    const [amount, setAmount] = useState("");
    const [reason, setReason] = useState(lead.lost_reasons[0] ?? "");
    const [busy, setBusy] = useState(false);
    const save = async () => {
        setBusy(true);
        try {
            await apiJson(`/api/crm/leads/${lead.id}/close`, { method: "POST", json: { outcome: open, amount: open === "won" && amount ? Number(amount) : null, reason: open === "lost" ? reason : "" } });
            onDone();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    return (
        <Dialog open={!!open} onClose={onClose} title={open === "won" ? "Won" : "Lost"} description={open === "won" ? "It's kept for good, even if they come back later." : "This shows you where leads go."}
                footer={<>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" disabled={busy} onClick={save}>Save</Button>
                </>}>
            {open === "won" ? (
                <label className="block">
                    <span className="text-xs text-stone-500">Amount in rupees (optional)</span>
                    <Input className="mt-1" type="number" inputMode="numeric" min={0} value={amount} onChange={(e) => setAmount(e.target.value)} />
                </label>
            ) : (
                <label className="block">
                    <span className="text-xs text-stone-500">Why</span>
                    <Select className="mt-1" value={reason} onChange={(e) => setReason(e.target.value)}>
                        {lead.lost_reasons.map((r) => <option key={r} value={r}>{r}</option>)}
                    </Select>
                </label>
            )}
        </Dialog>
    );
}

export default function LeadPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = use(params);
    const toast = useToast();
    const lead = useApi<LeadDetail>(`/api/crm/leads/${id}`);
    const [closing, setClosing] = useState<"won" | "lost" | null>(null);
    const [notes, setNotes] = useState("");
    const [tags, setTags] = useState<string[]>([]);
    const d = lead.data;
    const { reload } = lead;
    useEffect(() => { if (d) { setNotes(d.notes); setTags(d.tags); } }, [d]);

    if (lead.error) return <p className="text-sm text-signal">{lead.error}</p>;
    if (!d) return <Skeleton className="h-64" />;
    const change = async (values: Record<string, unknown>) => {
        try {
            await apiJson(`/api/crm/leads/${id}`, { method: "PUT", json: values });
            await reload();
        } catch (e) {
            toast((e as Error).message);
        }
    };
    const reopen = async () => {
        try {
            await apiJson(`/api/crm/leads/${id}/reopen`, { method: "POST" });
            await reload();
        } catch (e) {
            toast((e as Error).message);
        }
    };
    const real = async () => {
        try {
            await apiJson(`/api/crm/leads/${id}/real`, { method: "POST" });
            await reload();
        } catch (e) {
            toast((e as Error).message);
        }
    };
    const closed = d.stage === "customer" || d.stage === "lost";
    const whatsapp = d.e164 ? `https://wa.me/${d.e164.replace(/\D/g, "")}` : null;
    const details = Object.entries(d.details ?? {}).filter(([, v]) => typeof v === "string" || typeof v === "number");
    const from = (d.origin ?? {}) as Record<string, string>;
    const origin = ORIGIN.filter(([k]) => from[k]).map(([k, label]) => [label, k === "channel" ? CHANNEL[from[k]] ?? from[k] : from[k]]);
    return (
        <div className="space-y-5">
            <Link href="/dashboard/leads" className="inline-flex items-center gap-1 text-[13px] text-stone-500 hover:text-ink"><ArrowLeft size={13} aria-hidden /> Needs attention</Link>
            <Card className="p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                        <h2 className="text-lg font-semibold truncate">{d.name || d.phone || d.email}</h2>
                        <p className="text-[13px] text-stone-500 break-all">{[d.phone, d.email].filter(Boolean).join(" · ")}</p>
                        <p className="text-[13px] text-stone-500">{[sourceLabel(d.source), d.bot_name, d.last_enquiry_at ? `Asked ${inline(formatWhen(d.last_enquiry_at))}` : null].filter(Boolean).join(" · ")}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                        {d.e164 && <a href={`tel:${d.e164}`} data-agent="lead.call"><Button variant="primary"><Phone size={14} aria-hidden /> Call</Button></a>}
                        {whatsapp && <a href={whatsapp} target="_blank" rel="noopener noreferrer"><Button><MessageCircle size={14} aria-hidden /> WhatsApp</Button></a>}
                        {d.email && <a href={`mailto:${d.email}`}><Button><Mail size={14} aria-hidden /> Email</Button></a>}
                    </div>
                </div>
                <div className="grid sm:grid-cols-2 gap-3 mt-4">
                    <label className="block">
                        <span className="text-xs text-stone-500">Stage</span>
                        {closed ? <p className="text-sm mt-2">{STAGES[d.stage]}</p> : (
                            <Select className="mt-1" aria-label="Stage" value={d.stage} onChange={(e) => change({ stage: e.target.value })}>
                                {d.stages.filter((s) => s !== "customer" && s !== "lost").map((s) => <option key={s} value={s}>{STAGES[s] ?? s}</option>)}
                            </Select>
                        )}
                    </label>
                    <label className="block">
                        <span className="text-xs text-stone-500">Looked after by</span>
                        <Select className="mt-1" aria-label="Looked after by" disabled={!d.can_assign} value={d.assigned_to ?? ""} onChange={(e) => change({ assigned_to: e.target.value })}>
                            <option value="">Nobody yet</option>
                            {d.team.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                        </Select>
                    </label>
                </div>
                {d.quality === "junk" && (
                    <div className="flex flex-wrap items-center gap-3 mt-3">
                        <p className="text-[13px] text-stone-600 flex-1 min-w-48">Marked as junk{d.junk_reason ? `: ${d.junk_reason}` : ""}. Nobody was told and nobody contacted them.</p>
                        {d.can_assign && <Button size="sm" onClick={real}>It&apos;s a real lead</Button>}
                    </div>
                )}
                {d.enquiry_days_left !== null && !closed && (
                    <p className="text-[13px] text-stone-600 mt-3">
                        {d.enquiry_days_left > 0 ? `${d.enquiry_days_left} ${d.enquiry_days_left === 1 ? "day" : "days"} left of the 7 days their enquiry lets you contact them.` : "The 7 days their enquiry allows have passed. Contact them only if they've agreed or asked again."}
                    </p>
                )}
            </Card>

            {!closed && d.quality !== "junk" && <CanReach lead={d} onDone={() => { void reload(); }} />}

            <Card>
                <div className="px-5 pt-4 pb-3"><h3 className="text-sm font-medium">Next step</h3></div>
                {d.tasks.length ? <ul className="border-t border-line">{d.tasks.map((t) => <TaskRow key={t.id} task={t} onChanged={() => { void reload(); }} />)}</ul>
                    : !closed && <p className="px-5 pb-3 text-[13px] text-stone-500">Nothing planned yet.</p>}
                {!closed && <NewTask lead={d} onDone={() => { void reload(); }} />}
                {!closed && <HowItWent lead={d} onDone={() => { void reload(); }} />}
            </Card>

            <Promises lead={d} onChanged={() => { void reload(); }} />

            <Card>
                <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                    <div>
                        <h3 className="text-sm font-medium">Outcome</h3>
                        {!d.deals.length && <p className="text-[13px] text-stone-500 mt-0.5">Not closed yet.</p>}
                    </div>
                    <div className="flex gap-2">
                        {closed ? <Button onClick={reopen}>Reopen</Button> : <>
                            <Button onClick={() => setClosing("lost")}>Lost</Button>
                            <Button variant="primary" onClick={() => setClosing("won")}>Won</Button>
                        </>}
                    </div>
                </div>
                {!!d.deals.length && (
                    <ul className="border-t border-line">
                        {d.deals.map((x) => (
                            <li key={x.id} className={`flex items-center justify-between gap-3 px-5 py-2.5 border-t border-line first:border-t-0 text-[13px] ${x.reopened ? "text-stone-500" : ""}`}>
                                <span>{x.outcome === "won" ? `Won${x.amount ? `, ${rupees(x.amount)}` : ""}` : `Lost: ${x.reason ?? "no reason given"}`}{x.by ? ` · ${x.by}` : ""}{x.reopened ? " · reopened" : ""}</span>
                                {x.closed_at && <span className="text-stone-500 whitespace-nowrap">{formatWhen(x.closed_at)}</span>}
                            </li>
                        ))}
                    </ul>
                )}
            </Card>

            <div className="grid md:grid-cols-2 gap-5 items-start">
                <Card className="p-5 space-y-3">
                    <h3 className="text-sm font-medium">What you know</h3>
                    {d.brief && <p className="text-[13px] text-stone-700">{[d.brief.wants, d.brief.next && `Next: ${d.brief.next}`].filter(Boolean).join(". ")}</p>}
                    {!!details.length && <dl className="text-[13px] space-y-1">{details.map(([k, v]) => <div key={k} className="flex gap-2"><dt className="text-stone-500 shrink-0">{k}</dt><dd className="break-words min-w-0">{String(v)}</dd></div>)}</dl>}
                    {!!origin.length && <dl className="text-[13px] space-y-1 border-t border-line pt-2">{origin.map(([k, v]) => <div key={`${k}${v}`} className="flex gap-2"><dt className="text-stone-500 shrink-0">{k}</dt><dd className="break-all min-w-0">{v}</dd></div>)}</dl>}
                    <div>
                        <span className="text-xs text-stone-500">Tags</span>
                        <div className="mt-1"><PhraseInput keepCase value={tags} onChange={(v) => { setTags(v); void change({ tags: v }); }} label="Tags" placeholder="Add a tag" /></div>
                    </div>
                    <label className="block">
                        <span className="text-xs text-stone-500">Notes. The assistant reads these too.</span>
                        <Textarea className="mt-1" rows={3} maxLength={4000} value={notes} onChange={(e) => setNotes(e.target.value)} onBlur={() => { if (notes !== d.notes) void change({ notes }); }} />
                    </label>
                </Card>
                <Card>
                    <div className="px-5 pt-4 pb-3 border-b border-line"><h3 className="text-sm font-medium">What happened</h3></div>
                    {d.timeline.length ? <ul>{d.timeline.map((t, i) => <Step key={`${t.kind}-${t.at}-${i}`} item={t} />)}</ul> : <p className="px-5 py-4 text-[13px] text-stone-500">Nothing yet.</p>}
                </Card>
            </div>
            <Close key={closing ?? "none"} lead={d} open={closing} onClose={() => setClosing(null)} onDone={() => { setClosing(null); void reload(); }} />
        </div>
    );
}
