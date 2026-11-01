"use client";

import { useEffect, useState } from "react";
import { Pause, Play, Send, Trash2, X } from "lucide-react";
import { Button, Card, Dialog, Input, SaveBar, Segmented, Select, Skeleton, Status, Textarea, cn, useToast } from "@/components/ui";
import { EmailPreview } from "@/components/integrations/EmailPanel";
import { apiJson } from "@/lib/api";
import { BULK_STATUS, STAGE_LABEL, type BulkCount, type BulkEmail, type BulkEvent, type BulkPage, type BulkRules } from "@/lib/email";
import { useApi } from "@/lib/useApi";
import { parseUtc } from "@/lib/voice/api";

export const OPEN_STATUSES = ["scheduled", "testing", "sending", "paused"];
const ACTIVE = [{ value: "", label: "Any time" }, { value: "7", label: "In the last 7 days" }, { value: "30", label: "In the last 30 days" },
    { value: "90", label: "In the last 3 months" }, { value: "365", label: "In the last year" }];
const ENGAGED = [{ value: "", label: "Not needed" }, { value: "30", label: "In the last 30 days" }, { value: "90", label: "In the last 3 months" }];

/** Its status in words. A send due now waits for the next pass of the sender, up to half a minute: "Starting". */
export function statusOf(b: BulkEmail) {
    if (b.status === "scheduled" && b.send_at && parseUtc(b.send_at).getTime() <= Date.now()) return { label: "Starting", tone: "good" as const };
    return BULK_STATUS[b.status] ?? { label: b.status, tone: "neutral" as const };
}

export function atText(iso: string) {
    return parseUtc(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

/** {{first_name|there}} filled in, as the server does (backend mail/render.py). */
function fill(text: string, values: Record<string, string>) {
    return text.replace(/\{\{\s*(\w+)\s*(?:\|([^}]*))?\}\}/g, (_, key: string, fallback?: string) => values[key.toLowerCase()] || fallback || "");
}

function localValue(iso?: string | null) {
    if (!iso) return "";
    const d = parseUtc(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function today() {
    return localValue(new Date().toISOString()).slice(0, 10);
}

function Chips({ label, options, value, onChange }: { label: string; options: [string, string][]; value: string[]; onChange: (v: string[]) => void }) {
    if (options.length === 0) return null;
    return (
        <div>
            <span className="text-xs text-stone-500">{label}</span>
            <div role="group" aria-label={label} className="flex flex-wrap gap-1.5 mt-1">
                {options.map(([key, text]) => {
                    const on = value.includes(key);
                    return (
                        <button key={key} type="button" aria-pressed={on} onClick={() => onChange(on ? value.filter((v) => v !== key) : [...value, key])}
                                className={cn("h-7 px-2.5 rounded-full border text-[13px] transition-colors", on ? "border-plum bg-plum/5 text-ink" : "border-line text-stone-600 hover:text-ink")}>
                            {text}
                        </button>
                    );
                })}
            </div>
        </div>
    );
}

type Draft = { subject: string; subject_b: string | null; body: string; rules: BulkRules; event: BulkEvent | null; per_minute: number };
const draftOf = (b: BulkEmail): Draft => ({ subject: b.subject, subject_b: b.subject_b, body: b.body, rules: b.rules ?? {}, event: b.event, per_minute: b.per_minute });

function Who({ draft, set, page, count, botId, onChanged }: {
    draft: Draft; set: (d: Draft) => void; page: BulkPage; count: BulkCount | null; botId: string; onChanged: () => void;
}) {
    const toast = useToast();
    const [name, setName] = useState("");
    const rules = draft.rules;
    const rule = (key: keyof BulkRules, value: string[] | number | undefined) => {
        const next: BulkRules = { ...rules, [key]: value };
        if (!value || (Array.isArray(value) && value.length === 0)) delete next[key];
        set({ ...draft, rules: next });
    };
    const keep = async () => {
        try {
            await apiJson("/api/email/segments", { method: "POST", json: { bot_id: botId, name: name.trim(), rules } });
            setName("");
            onChanged();
            toast("Group saved");
        } catch (e) {
            toast((e as Error).message);
        }
    };
    const drop = async (id: string) => {
        try {
            await apiJson(`/api/email/segments/${id}`, { method: "DELETE" });
            onChanged();
        } catch (e) {
            toast((e as Error).message);
        }
    };
    const left = count?.left_out;
    return (
        <Card className="p-5 space-y-4">
            <div>
                <h3 className="text-sm font-medium">Who gets it</h3>
                <p className="text-[13px] text-stone-500 mt-0.5">Only people who agreed to offers and news. Narrow it, or leave it as everyone who agreed.</p>
            </div>
            {page.segments.length > 0 && (
                <div>
                    <span className="text-xs text-stone-500">Saved groups</span>
                    <div className="flex flex-wrap gap-1.5 mt-1">
                        {page.segments.map((g) => (
                            <span key={g.id} className="inline-flex items-center rounded-full border border-line text-[13px]">
                                <button type="button" className="h-7 pl-2.5 pr-1.5 hover:text-plum" onClick={() => set({ ...draft, rules: g.rules })}>{g.name}</button>
                                <button type="button" aria-label={`Delete the group ${g.name}`} className="h-7 pr-2 text-stone-400 hover:text-ink" onClick={() => drop(g.id)}><X size={12} aria-hidden /></button>
                            </span>
                        ))}
                    </div>
                </div>
            )}
            <Chips label="Lead status" options={Object.entries(page.statuses)} value={rules.statuses ?? []} onChange={(v) => rule("statuses", v)} />
            <Chips label="Stage" options={page.stages.map((s) => [s, STAGE_LABEL[s] ?? s])} value={rules.stages ?? []} onChange={(v) => rule("stages", v)} />
            <Chips label="Came from" options={Object.entries(page.sources)} value={rules.sources ?? []} onChange={(v) => rule("sources", v)} />
            <Chips label="Tags" options={page.tags.map((t) => [t, t])} value={rules.tags ?? []} onChange={(v) => rule("tags", v)} />
            <div className="grid sm:grid-cols-2 gap-3">
                <label className="block">
                    <span className="text-xs text-stone-500">In touch</span>
                    <Select className="mt-1" aria-label="In touch" value={String(rules.active_days ?? "")} onChange={(e) => rule("active_days", e.target.value ? Number(e.target.value) : undefined)}>
                        {ACTIVE.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </Select>
                </label>
                <label className="block">
                    <span className="text-xs text-stone-500">Clicked or replied to an email</span>
                    <Select className="mt-1" aria-label="Clicked or replied" value={String(rules.engaged_days ?? "")} onChange={(e) => rule("engaged_days", e.target.value ? Number(e.target.value) : undefined)}>
                        {ENGAGED.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </Select>
                </label>
            </div>
            <div className="rounded-md bg-paper border border-line px-4 py-3" aria-live="polite">
                {count === null ? <Skeleton className="h-5 w-40" /> : (
                    <>
                        <p className="text-sm"><span className="font-medium tabular-nums">{count.count}</span> {count.count === 1 ? "person" : "people"} will get it</p>
                        {left && left.no_consent + left.stopped + left.throwaway > 0 && (
                            <p className="text-[13px] text-stone-500 mt-0.5">
                                Left out: {[left.no_consent && `${left.no_consent} haven't agreed to offers`, left.stopped && `${left.stopped} stopped your emails`,
                                    left.throwaway && `${left.throwaway} throwaway addresses`].filter(Boolean).join(", ")}.
                            </p>
                        )}
                    </>
                )}
            </div>
            <div className="flex flex-wrap gap-2">
                <Input aria-label="Group name" className="flex-1 min-w-40" maxLength={120} value={name} placeholder="Name these rules to use them again" onChange={(e) => setName(e.target.value)} />
                <Button size="sm" disabled={!name.trim()} onClick={keep}>Save as a group</Button>
            </div>
        </Card>
    );
}

function Editor({ b, page, botId, onBack, onChanged, reload }: { b: BulkEmail; page: BulkPage; botId: string; onBack: () => void; onChanged: () => void; reload: () => void }) {
    const toast = useToast();
    const [saved, setSaved] = useState(draftOf(b));
    const [draft, setDraft] = useState(draftOf(b));
    const [notes, setNotes] = useState<string[]>(b.notes ?? []);
    const [count, setCount] = useState<BulkCount | null>(null);
    const [busy, setBusy] = useState<string | null>(null);
    const [asking, setAsking] = useState(false);
    const [removing, setRemoving] = useState(false);
    const [when, setWhen] = useState<"now" | "later" | "usual">("now");
    const [at, setAt] = useState("");
    const [day, setDay] = useState(today());
    const changed = JSON.stringify(draft) !== JSON.stringify(saved);
    const rulesKey = JSON.stringify(draft.rules);

    useEffect(() => {
        let live = true;
        setCount(null);
        const t = setTimeout(() => {
            apiJson<BulkCount>("/api/email/bulk/count", { method: "POST", json: { bot_id: botId, rules: JSON.parse(rulesKey) } })
                .then((c) => live && setCount(c)).catch(() => live && setCount({ count: 0, left_out: { no_consent: 0, stopped: 0, throwaway: 0 }, sample: [] }));
        }, 300);
        return () => { live = false; clearTimeout(t); };
    }, [rulesKey, botId]);

    const save = async (): Promise<boolean> => {
        setBusy("save");
        try {
            const done = await apiJson<BulkEmail>(`/api/email/broadcasts/${b.id}`, { method: "PUT", json: draft });
            setSaved(draftOf(done));
            setDraft(draftOf(done));
            setNotes(done.notes ?? []);
            onChanged();
            return true;
        } catch (e) {
            toast((e as Error).message);
            return false;
        } finally {
            setBusy(null);
        }
    };
    const test = async () => {
        if (changed && !(await save())) return;
        setBusy("test");
        try {
            const done = await apiJson<{ to: string }>(`/api/email/broadcasts/${b.id}/test`, { method: "POST", json: {} });
            toast(`A test went to ${done.to}`);
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(null);
        }
    };
    const send = async () => {
        if (changed && !(await save())) return;
        const start = new Date(`${day}T00:00`);
        const json = when === "now" ? { usual_hour: false } : when === "later" ? { at: new Date(at).toISOString(), usual_hour: false }
            : { at: (start < new Date() ? new Date() : start).toISOString(), usual_hour: true };
        setBusy("send");
        try {
            await apiJson(`/api/email/broadcasts/${b.id}/send`, { method: "POST", json });
            setAsking(false);
            toast(when === "now" ? "It's going out" : "Scheduled");
            onChanged();
            reload();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(null);
        }
    };
    const remove = async () => {
        try {
            await apiJson(`/api/email/broadcasts/${b.id}`, { method: "DELETE" });
            onChanged();
            onBack();
        } catch (e) {
            toast((e as Error).message);
        }
    };

    const person = count?.sample[0];
    const values = { name: person?.name || "Priya Raman", first_name: (person?.name || "Priya Raman").split(" ")[0], email: person?.email || "priya@example.com", business: page.sender.name };
    const invitation = draft.event?.title ? `\n\n${[draft.event.title, draft.event.at ? atText(new Date(draft.event.at).toISOString()) : "", draft.event.where].filter(Boolean).join("\n")}\n\nWill you come? (a link to answer Yes, Maybe or No)` : "";
    const test_ab = !!draft.subject_b?.trim();
    const people = count?.count ?? 0;
    const ready = draft.subject.trim() && draft.body.trim() && people > 0 && (!test_ab || people >= page.test_min);
    return (
        <div className="space-y-5">
            <button type="button" onClick={onBack} className="text-sm text-plum hover:underline">Back to bulk email</button>
            <Who draft={draft} set={setDraft} page={page} count={count} botId={botId} onChanged={onChanged} />
            <Card className="p-5">
                <div className="grid lg:grid-cols-2 gap-6">
                    <div className="space-y-3 min-w-0">
                        <h3 className="text-sm font-medium">The email</h3>
                        <label className="block">
                            <span className="text-xs text-stone-500">Subject</span>
                            <Input className="mt-1" maxLength={200} value={draft.subject} onChange={(e) => setDraft({ ...draft, subject: e.target.value })} />
                        </label>
                        <label className="flex items-start gap-2 text-[13px] text-stone-700">
                            <input type="checkbox" className="mt-0.5" checked={draft.subject_b !== null} onChange={(e) => setDraft({ ...draft, subject_b: e.target.checked ? "" : null })} />
                            <span>Try a second subject. A fifth of the list gets one of the two; after 4 hours the one with more clicks and replies goes to everyone else. Needs {page.test_min} people or more.</span>
                        </label>
                        {draft.subject_b !== null && (
                            <label className="block">
                                <span className="text-xs text-stone-500">Second subject</span>
                                <Input className="mt-1" maxLength={200} value={draft.subject_b} onChange={(e) => setDraft({ ...draft, subject_b: e.target.value })} />
                            </label>
                        )}
                        <label className="block">
                            <span className="text-xs text-stone-500">Message</span>
                            <Textarea className="mt-1" rows={9} maxLength={10000} value={draft.body} onChange={(e) => setDraft({ ...draft, body: e.target.value })} />
                            <span className="block text-xs text-stone-500 mt-1">Fills in by itself: {"{{first_name|there}}"}, {"{{name}}"}, {"{{business}}"}. Links are tracked, so you see who clicked.</span>
                        </label>
                        <label className="flex items-center gap-2 text-[13px] text-stone-700">
                            <input type="checkbox" checked={!!draft.event} onChange={(e) => setDraft({ ...draft, event: e.target.checked ? { title: "", at: "", where: "" } : null })} />
                            It&apos;s an invitation: people answer Yes, Maybe or No, and those coming get a reminder the day before
                        </label>
                        {draft.event && (
                            <div className="grid sm:grid-cols-2 gap-3">
                                <label className="block sm:col-span-2">
                                    <span className="text-xs text-stone-500">What</span>
                                    <Input className="mt-1" maxLength={200} value={draft.event.title} placeholder="Open house at Sunrise Homes" onChange={(e) => setDraft({ ...draft, event: { ...draft.event!, title: e.target.value } })} />
                                </label>
                                <label className="block">
                                    <span className="text-xs text-stone-500">When</span>
                                    <Input className="mt-1" type="datetime-local" value={localValue(draft.event.at)} onChange={(e) => setDraft({ ...draft, event: { ...draft.event!, at: e.target.value ? new Date(e.target.value).toISOString() : "" } })} />
                                </label>
                                <label className="block">
                                    <span className="text-xs text-stone-500">Where</span>
                                    <Input className="mt-1" maxLength={300} value={draft.event.where ?? ""} placeholder="Anna Nagar site office" onChange={(e) => setDraft({ ...draft, event: { ...draft.event!, where: e.target.value } })} />
                                </label>
                            </div>
                        )}
                        <label className="block">
                            <span className="text-xs text-stone-500">How fast it goes</span>
                            <Select className="mt-1 w-56" aria-label="How fast it goes" value={draft.per_minute} onChange={(e) => setDraft({ ...draft, per_minute: Number(e.target.value) })}>
                                {page.paces.map((p) => <option key={p} value={p}>{p} emails a minute</option>)}
                            </Select>
                        </label>
                    </div>
                    <EmailPreview from={`${page.sender.name} <${page.sender.address}>`} replyTo={page.sender.reply_to ?? undefined}
                                  subject={fill(draft.subject, values)} body={fill(draft.body, values) + invitation} />
                </div>
                {notes.length > 0 && !changed && (
                    <div className="mt-5 rounded-md border border-line-strong px-4 py-3">
                        <p className="text-[13px] font-medium">Before you send</p>
                        <ul className="mt-1 text-[13px] text-stone-600 list-disc pl-5 space-y-0.5">{notes.map((n) => <li key={n}>{n}</li>)}</ul>
                    </div>
                )}
            </Card>
            <div className="flex flex-wrap items-center gap-2">
                <Button variant="primary" disabled={!ready || !!busy} onClick={() => setAsking(true)}><Send size={14} aria-hidden /> Send…</Button>
                <Button disabled={!draft.subject.trim() || !draft.body.trim() || !!busy} onClick={test}>{busy === "test" ? "Sending…" : "Send a test to me"}</Button>
                <Button variant="ghost" className="ml-auto" onClick={() => setRemoving(true)}><Trash2 size={14} aria-hidden /> Delete draft</Button>
            </div>
            <Dialog open={asking} onClose={() => setAsking(false)} title={`Send to ${people} ${people === 1 ? "person" : "people"}?`}
                    description={`From ${page.sender.name} <${page.sender.address}>, to everyone in this group who agreed to offers and news.`}
                    footer={<>
                        <Button variant="ghost" onClick={() => setAsking(false)}>Cancel</Button>
                        <Button variant="primary" disabled={!!busy || (when === "later" && !at)} onClick={send}>{busy === "send" ? "Sending…" : when === "now" ? "Send now" : "Schedule it"}</Button>
                    </>}>
                <div className="space-y-3">
                    <Segmented label="When" value={when} onChange={setWhen}
                               options={[{ value: "now", label: "Now" }, { value: "later", label: "At a time" }, { value: "usual", label: "Their usual hour" }]} />
                    {when === "later" && <Input type="datetime-local" aria-label="Send at" value={at} onChange={(e) => setAt(e.target.value)} />}
                    {when === "usual" && (
                        <div className="space-y-1">
                            <Input type="date" aria-label="On" value={day} min={today()} onChange={(e) => setDay(e.target.value)} />
                            <p className="text-xs text-stone-500">Each person gets it at about the hour they last picked up your call, between 9 am and 8 pm.</p>
                        </div>
                    )}
                    <p className="text-[13px] text-stone-600">
                        {test_ab ? "A fifth of them get one of your two subjects first; the rest get the better one 4 hours later. " : ""}
                        It goes {draft.per_minute} a minute, and you can pause it while it&apos;s going out. It pauses by itself if people report it as spam or many addresses bounce.
                    </p>
                </div>
            </Dialog>
            <Dialog open={removing} onClose={() => setRemoving(false)} title="Delete this draft?"
                    footer={<>
                        <Button variant="ghost" onClick={() => setRemoving(false)}>Keep it</Button>
                        <Button variant="primary" onClick={remove}>Delete</Button>
                    </>}>
                <span />
            </Dialog>
            <SaveBar visible={changed} saving={busy === "save"} onDiscard={() => setDraft(saved)} onSave={() => { void save(); }} />
        </div>
    );
}

function Report({ b, onBack, onChanged, reload }: { b: BulkEmail; onBack: () => void; onChanged: () => void; reload: () => void }) {
    const toast = useToast();
    const [busy, setBusy] = useState(false);
    const s = statusOf(b);
    const c = b.counts;
    const act = async (action: "pause" | "resume" | "cancel") => {
        setBusy(true);
        try {
            await apiJson(`/api/email/broadcasts/${b.id}/${action}`, { method: "POST", json: {} });
            toast(action === "pause" ? "Paused" : action === "resume" ? "Going out again" : "Cancelled: nothing more goes");
            onChanged();
            reload();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    const going = ["scheduled", "testing", "sending"].includes(b.status);
    const tiles: [string, number][] = c ? [["People", b.recipients], ["Delivered", c.delivered], ["Clicked", c.clicked], ["Replied", c.replied], ["Unsubscribed", c.unsubscribed],
        ["Spam reports", c.complained], ["Bounced", c.bounced], ["Waiting", c.queued + c.held], ["Failed", c.failed]] : [];
    return (
        <div className="space-y-5">
            <button type="button" onClick={onBack} className="text-sm text-plum hover:underline">Back to bulk email</button>
            <Card className="p-5">
                <div className="flex flex-wrap items-start gap-3">
                    <div className="flex-1 min-w-48">
                        <h3 className="text-base font-medium break-words">{b.subject}</h3>
                        <p className="text-[13px] text-stone-500 mt-1">
                            {s.label === "Starting" ? "It starts within a minute" : b.status === "scheduled" && b.send_at ? `Goes ${b.usual_hour ? "at each person's usual hour, from" : "on"} ${atText(b.send_at)}` :
                                b.started_at ? `Started ${atText(b.started_at)}${b.finished_at ? `, finished ${atText(b.finished_at)}` : ""}` : b.created_at ? `Written ${atText(b.created_at)}` : ""}
                            {b.status === "testing" && b.test_ends_at ? `. Testing two subjects until ${atText(b.test_ends_at)}` : ""}
                        </p>
                    </div>
                    <Status tone={s.tone}>{s.label}</Status>
                </div>
                {b.status === "paused" && (
                    <div className="mt-4 rounded-md border border-line-strong px-4 py-3 flex flex-wrap items-center gap-3">
                        <p className="text-[13px] text-stone-700 flex-1 min-w-48">{b.paused_why}</p>
                        <Button size="sm" variant="primary" disabled={busy} onClick={() => act("resume")}><Play size={13} aria-hidden /> Resume</Button>
                        <Button size="sm" variant="ghost" disabled={busy} onClick={() => act("cancel")}>Cancel the rest</Button>
                    </div>
                )}
                {going && (
                    <div className="mt-4 flex flex-wrap gap-2">
                        <Button size="sm" disabled={busy} onClick={() => act("pause")}><Pause size={13} aria-hidden /> Pause</Button>
                        <Button size="sm" variant="ghost" disabled={busy} onClick={() => act("cancel")}>Cancel the rest</Button>
                    </div>
                )}
                {c && (
                    <dl className="mt-5 grid grid-cols-3 sm:grid-cols-5 lg:grid-cols-9 gap-3">
                        {tiles.map(([label, value]) => (
                            <div key={label} className="rounded-md border border-line px-3 py-2">
                                <dt className="text-xs text-stone-500">{label}</dt>
                                <dd className="text-lg tabular-nums">{value}</dd>
                            </div>
                        ))}
                    </dl>
                )}
                {!!b.no_mail_server && <p className="text-[13px] text-stone-600 mt-3">{b.no_mail_server} {b.no_mail_server === 1 ? "address was" : "addresses were"} left out: their domain doesn&apos;t receive email.</p>}
                <p className="text-xs text-stone-500 mt-2">Opens aren&apos;t counted: mail apps open emails by themselves, so they say little.</p>
            </Card>
            {b.variants && b.subject_b && (
                <Card>
                    <div className="px-5 pt-4 pb-3"><h3 className="text-sm font-medium">The subject test</h3></div>
                    <ul>
                        {(["a", "b"] as const).map((k) => {
                            const v = b.variants![k];
                            return (
                                <li key={k} className="flex flex-wrap items-center gap-3 px-5 py-3 border-t border-line text-sm">
                                    <span className="flex-1 min-w-48 break-words">{k === "a" ? b.subject : b.subject_b}</span>
                                    <span className="text-[13px] text-stone-500 tabular-nums">{v.sent} sent · {v.clicked} clicked · {v.replied} replied</span>
                                    {b.winner === k && <Status tone="good">Chosen</Status>}
                                </li>
                            );
                        })}
                    </ul>
                </Card>
            )}
            {b.rsvp && (
                <Card className="p-5">
                    <h3 className="text-sm font-medium">{b.event?.title}</h3>
                    <p className="text-[13px] text-stone-600 mt-1 tabular-nums">{b.rsvp.yes} coming · {b.rsvp.maybe} maybe · {b.rsvp.no} can&apos;t come</p>
                </Card>
            )}
            <Card className="p-5">
                <h3 className="text-sm font-medium">What it said</h3>
                <p className="text-xs text-stone-500 mt-0.5">As you wrote it: each person&apos;s name was filled in.</p>
                <p className="text-[13px] text-stone-700 mt-2 whitespace-pre-wrap break-words">{b.body}</p>
            </Card>
        </div>
    );
}

/** One bulk email: a draft to write and send, or how a sent one did. */
export function BulkEditor({ id, page, botId, onBack, onChanged }: { id: string; page: BulkPage; botId: string; onBack: () => void; onChanged: () => void }) {
    const one = useApi<BulkEmail>(`/api/email/broadcasts/${id}`);
    const { reload } = one;
    const status = one.data?.status;
    useEffect(() => {
        if (!status || !OPEN_STATUSES.includes(status)) return;
        const t = setInterval(() => { void reload(); }, 10_000);
        return () => clearInterval(t);
    }, [status, reload]);
    if (one.error) return <p className="text-sm text-signal">{one.error}</p>;
    if (!one.data) return <Skeleton className="h-96" />;
    return one.data.status === "draft"
        ? <Editor key={one.data.id} b={one.data} page={page} botId={botId} onBack={onBack} onChanged={onChanged} reload={() => { void reload(); }} />
        : <Report b={one.data} onBack={onBack} onChanged={onChanged} reload={() => { void reload(); }} />;
}
