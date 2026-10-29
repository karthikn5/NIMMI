"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronRight, PhoneIncoming, PhoneOutgoing, Search } from "lucide-react";
import { Button, Card, Dialog, EmptyState, Input, Select, Sheet, Skeleton, Status, Switch, Textarea, useToast } from "@/components/ui";
import { NewCallDialog } from "@/components/voice/schedule/Calls";
import { apiSave, useApi } from "@/lib/useApi";
import { OUTCOMES, formatNumber, formatWhen } from "@/lib/voice/api";
import { ITEM_STATUS, KINDS, LEADS, LEAD_ORDER, MEETING_KINDS, MEETING_STATUS, formatSlot, scheduleChanged } from "@/lib/voice/schedule";
import type { ContactDetail, ContactSummary, LeadStatus, MeetingSummary, ScheduleItem, VoiceAgentSummary } from "@/lib/voice/types";

/** Everyone the assistants have spoken to on the phone, by number: what they remember on the next call. */
export default function ContactsPage() {
    const agents = useApi<VoiceAgentSummary[]>("/api/voice/agents");
    const [bot, setBot] = useState("");
    const [typed, setTyped] = useState("");
    const [q, setQ] = useState("");
    const [openId, setOpenId] = useState<string | null>(null);
    const [lead, setLead] = useState<"" | LeadStatus | "none">("");
    useEffect(() => { const t = setTimeout(() => setQ(typed.trim()), 300); return () => clearTimeout(t); }, [typed]);
    const contacts = useApi<ContactSummary[]>(`/api/voice/contacts?bot_id=${encodeURIComponent(bot)}&q=${encodeURIComponent(q)}`);
    const shown = (contacts.data ?? []).filter((c) => !lead || (lead === "none" ? !c.lead_status : c.lead_status === lead));

    return (
        <>
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-3 mb-4">
                <div>
                    <h2 className="text-[15px] font-semibold">Contacts</h2>
                    <p className="text-[13px] text-stone-500 mt-0.5 max-w-xl">
                        People your assistants have spoken to on the phone. When they call again, or are called, the assistant greets
                        them by name and remembers what earlier calls were about.
                    </p>
                </div>
                <div className="flex flex-wrap gap-2">
                    <Select aria-label="Lead" className="w-auto" value={lead} onChange={(e) => setLead(e.target.value as typeof lead)}>
                        <option value="">All leads</option>
                        {LEAD_ORDER.map((l) => <option key={l} value={l}>{LEADS[l].label}</option>)}
                        <option value="none">Not rated</option>
                    </Select>
                    {(agents.data?.length ?? 0) > 1 && (
                        <Select aria-label="Assistant" className="w-auto" value={bot} onChange={(e) => setBot(e.target.value)}>
                            <option value="">All assistants</option>
                            {agents.data?.map((a) => <option key={a.bot_id} value={a.bot_id}>{a.bot_name}</option>)}
                        </Select>
                    )}
                    <div className="relative">
                        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-stone-400" aria-hidden />
                        <Input aria-label="Search by name or number" className="pl-8 w-56" placeholder="Name or number"
                               value={typed} onChange={(e) => setTyped(e.target.value)} />
                    </div>
                </div>
            </div>

            <Card>
                {contacts.loading ? (
                    <div className="p-5 space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>
                ) : contacts.error ? (
                    <p className="p-5 text-sm text-signal">Couldn&apos;t load contacts. {contacts.error}</p>
                ) : !shown.length ? (
                    <EmptyState
                        title={q || lead ? "No one matches that" : "No contacts yet"}
                        body={q || lead ? "Try part of their name or number, or another lead rating." : "After each phone call, the caller appears here with what they told the assistant."}
                    />
                ) : (
                    <table className="w-full text-sm">
                        <thead className="hidden md:table-header-group">
                            <tr className="text-left text-[13px] text-stone-500">
                                <th className="font-normal px-5 py-3">Name</th>
                                <th className="font-normal px-3 py-3">Number</th>
                                <th className="font-normal px-3 py-3">Assistant</th>
                                <th className="font-normal px-3 py-3">Lead</th>
                                <th className="font-normal px-3 py-3 text-right">Calls</th>
                                <th className="font-normal px-3 py-3">Last call</th>
                                <th className="w-10" />
                            </tr>
                        </thead>
                        <tbody>
                            {shown.map((c) => (
                                <tr key={c.id} className="group border-t border-line first:border-t-0 md:first:border-t hover:bg-stone-50 transition-colors relative">
                                    <td className="px-5 py-3.5">
                                        <button type="button" onClick={() => setOpenId(c.id)}
                                                className="font-medium text-left after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-plum focus-visible:after:-outline-offset-2">
                                            {c.name || <span className="text-stone-500 font-normal">Name not given</span>}
                                        </button>
                                        <p className="md:hidden text-[13px] text-stone-500 mt-1 tabular-nums">
                                            {[c.number, `${c.calls} call${c.calls === 1 ? "" : "s"}`, c.lead_status && LEADS[c.lead_status].label].filter(Boolean).join(" · ")}
                                        </p>
                                    </td>
                                    <td className="hidden md:table-cell px-3 py-3.5 tabular-nums text-stone-700">{c.number}</td>
                                    <td className="hidden md:table-cell px-3 py-3.5 text-stone-700">{c.bot_name}</td>
                                    <td className="hidden md:table-cell px-3 py-3.5">
                                        {c.lead_status ? <Status tone={LEADS[c.lead_status].tone}>{LEADS[c.lead_status].label}</Status> : <span className="text-stone-400">–</span>}
                                    </td>
                                    <td className="hidden md:table-cell px-3 py-3.5 text-right tabular-nums">{formatNumber(c.calls)}</td>
                                    <td className="hidden md:table-cell px-3 py-3.5 text-stone-700">{c.last_call_at ? formatWhen(c.last_call_at) : ""}</td>
                                    <td className="px-3 py-3.5 text-right"><ChevronRight size={16} className="inline text-stone-300 group-hover:text-stone-500" aria-hidden /></td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </Card>

            <ContactSheet id={openId} onClose={() => setOpenId(null)} onChanged={contacts.reload} />
        </>
    );
}

function ContactSheet({ id, onClose, onChanged }: { id: string | null; onClose: () => void; onChanged: () => void }) {
    const toast = useToast();
    const contact = useApi<ContactDetail>(id ? `/api/voice/contacts/${id}` : null);
    const [form, setForm] = useState({ name: "", email: "", notes: "" });
    const [saving, setSaving] = useState(false);
    const [forgetting, setForgetting] = useState(false);
    const c = id ? contact.data : null;

    useEffect(() => {
        if (contact.data) setForm({ name: contact.data.name, email: contact.data.email, notes: contact.data.notes });
    }, [contact.data]);

    const changed = !!c && (form.name !== c.name || form.email !== c.email || form.notes !== c.notes);
    const saveForm = async () => {
        setSaving(true);
        const res = await apiSave(`/api/voice/contacts/${id}`, "PATCH", form);
        setSaving(false);
        if (!res.ok) return toast(res.message);
        toast("Saved");
        contact.reload();
        onChanged();
    };
    const forget = async () => {
        const res = await apiSave(`/api/voice/contacts/${id}/forget`, "POST");
        setForgetting(false);
        if (!res.ok) return toast(res.message);
        toast("Forgotten. The assistant won't use what it knew about them.");
        onChanged();
        onClose();
    };

    return (
        <Sheet open={!!id} onClose={onClose} title={c?.name || c?.number || "Contact"} subtitle={c ? `${c.number} · ${c.bot_name}` : undefined}>
            {!c ? (
                <div className="p-6 space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}</div>
            ) : (
                <div className="px-6 py-5 space-y-6">
                    <LeadSection contact={c} onChanged={() => { contact.reload(); onChanged(); }} />
                    <section className="space-y-3">
                        <div className="grid sm:grid-cols-2 gap-3">
                            <div>
                                <label htmlFor="c-name" className="text-[13px] text-stone-600">Name</label>
                                <Input id="c-name" className="mt-1" maxLength={80} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                            </div>
                            <div>
                                <label htmlFor="c-email" className="text-[13px] text-stone-600">Email</label>
                                <Input id="c-email" className="mt-1" type="email" maxLength={120} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
                            </div>
                        </div>
                        <div>
                            <label htmlFor="c-notes" className="text-[13px] text-stone-600">Notes for the assistant</label>
                            <Textarea id="c-notes" className="mt-1" rows={3} maxLength={1000} value={form.notes}
                                      placeholder="e.g. Prefers Tamil. Interested in the weekend batch."
                                      onChange={(e) => setForm({ ...form, notes: e.target.value })} />
                            <p className="text-xs text-stone-500 mt-1">The assistant reads these on their next call. It never reads out their email or number.</p>
                        </div>
                        <div className="flex justify-end">
                            <Button variant="primary" size="sm" disabled={!changed || saving} onClick={saveForm}>{saving ? "Saving…" : "Save"}</Button>
                        </div>
                    </section>

                    {Object.keys(c.details).length > 0 && (
                        <section>
                            <h3 className="text-sm font-medium">What they told the assistant</h3>
                            <dl className="mt-2 grid grid-cols-[minmax(0,10rem)_1fr] gap-x-4 gap-y-1.5 text-[13px]">
                                {Object.entries(c.details).map(([k, v]) => (
                                    <div key={k} className="contents">
                                        <dt className="text-stone-500">{k}</dt>
                                        <dd className="text-ink break-words">{v}</dd>
                                    </div>
                                ))}
                            </dl>
                        </section>
                    )}

                    <section>
                        <h3 className="text-sm font-medium">Calls</h3>
                        {c.history.length === 0 ? (
                            <p className="text-[13px] text-stone-500 mt-2">No calls kept.</p>
                        ) : (
                            <ol className="mt-2 space-y-3">
                                {c.history.map((h) => (
                                    <li key={h.id} className="text-[13px]">
                                        <div className="flex flex-wrap items-center gap-2 text-stone-500">
                                            {h.direction === "inbound" ? <PhoneIncoming size={12} aria-hidden /> : <PhoneOutgoing size={12} aria-hidden />}
                                            <span>{h.direction === "inbound" ? "They called" : "Assistant called"}</span>
                                            {h.started_at && <span>· {formatWhen(h.started_at)}</span>}
                                            <Status tone={OUTCOMES[h.outcome]?.tone ?? "neutral"}>{OUTCOMES[h.outcome]?.label ?? h.outcome}</Status>
                                            {!h.remembered && <span className="text-stone-400">· Forgotten</span>}
                                        </div>
                                        {h.summary && <p className="text-ink mt-1 leading-relaxed">{h.summary}</p>}
                                    </li>
                                ))}
                            </ol>
                        )}
                    </section>

                    <section className="border-t border-line pt-5">
                        <Button variant="ghost" size="sm" onClick={() => setForgetting(true)}>Forget this caller</Button>
                        <p className="text-xs text-stone-500 mt-1.5">
                            The assistant stops using their name, details, notes and earlier calls. Their calls stay in Calls; to delete
                            everything about a number, use Compliance.
                        </p>
                    </section>
                </div>
            )}
            <Dialog
                open={forgetting}
                onClose={() => setForgetting(false)}
                title="Forget this caller?"
                description="On their next call, the assistant treats them as someone new."
                footer={<>
                    <Button variant="ghost" onClick={() => setForgetting(false)}>Cancel</Button>
                    <Button variant="primary" onClick={forget}>Forget</Button>
                </>}
            >
                <p className="text-[13px] text-stone-600">This can&apos;t be undone.</p>
            </Dialog>
        </Sheet>
    );
}

/** Their lead rating (the assistant's after each call, or the team's), follow-ups, and what's coming up for them. */
function LeadSection({ contact: c, onChanged }: { contact: ContactDetail; onChanged: () => void }) {
    const toast = useToast();
    const next = useApi<{ calls: ScheduleItem[]; meeting: MeetingSummary | null }>(`/api/voice/schedule/contacts/${c.id}/next`);
    const [busy, setBusy] = useState(false);
    const [scheduling, setScheduling] = useState(false);

    const update = async (body: { lead_status?: LeadStatus; follow_ups_off?: boolean }, done: string) => {
        setBusy(true);
        const res = await apiSave(`/api/voice/schedule/contacts/${c.id}`, "PATCH", body);
        setBusy(false);
        if (!res.ok) return toast(res.message);
        toast(done);
        next.reload();
        onChanged();
        scheduleChanged();
    };
    const coming = next.data;

    return (
        <section className="space-y-3">
            <div className="flex flex-wrap items-end gap-3">
                <div>
                    <label htmlFor="c-lead" className="text-[13px] text-stone-600">Lead</label>
                    <Select id="c-lead" className="mt-1 w-auto" value={c.lead_status ?? ""} disabled={busy}
                            onChange={(e) => e.target.value && update({ lead_status: e.target.value as LeadStatus }, "Saved")}>
                        {!c.lead_status && <option value="">Not rated yet</option>}
                        {LEAD_ORDER.map((l) => <option key={l} value={l}>{LEADS[l].label}: {LEADS[l].about.toLowerCase()}</option>)}
                    </Select>
                </div>
                <label className="flex items-center gap-2.5 text-[13px] text-stone-700 h-9">
                    <Switch checked={!c.follow_ups_off} disabled={busy} label="Follow-ups for this person"
                            onChange={(v) => update({ follow_ups_off: !v }, v ? "Follow-ups on for them" : "No more follow-ups for them")} />
                    Follow-ups
                </label>
                <Button size="sm" className="ml-auto" onClick={() => setScheduling(true)}>Schedule a call</Button>
            </div>
            {c.lead_status && (
                <p className="text-xs text-stone-500">
                    {c.lead_set_by_team ? "Set by your team." : `Rated by the assistant${c.lead_reason ? `: ${c.lead_reason}` : "."}`}
                    {c.follow_ups > 0 && ` ${c.follow_ups} follow-up call${c.follow_ups === 1 ? "" : "s"} so far.`}
                </p>
            )}
            {coming && (coming.calls.length > 0 || coming.meeting) && (
                <ul className="border border-line rounded-md divide-y divide-line text-[13px]">
                    {coming.meeting && (
                        <li className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                            <Link href={`/dashboard/voice/schedule?tab=meetings&meeting=${coming.meeting.id}`} className="text-plum hover:underline underline-offset-4">
                                {MEETING_KINDS[coming.meeting.kind]} meeting, {formatSlot(coming.meeting.local, coming.meeting.timezone)}
                            </Link>
                            <Status tone={MEETING_STATUS[coming.meeting.status].tone}>{MEETING_STATUS[coming.meeting.status].label}</Status>
                        </li>
                    )}
                    {coming.calls.map((i) => (
                        <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                            <Link href={`/dashboard/voice/schedule?tab=calls&item=${i.id}`} className="text-plum hover:underline underline-offset-4 min-w-0 truncate">
                                {KINDS[i.kind].label}{i.status === "todo" ? "" : `, ${formatSlot(i.local, i.timezone)}`}
                            </Link>
                            <Status tone={ITEM_STATUS[i.status].tone}>{ITEM_STATUS[i.status].label}</Status>
                        </li>
                    ))}
                </ul>
            )}
            <NewCallDialog open={scheduling} botId={c.bot_id} contact={{ id: c.id, label: c.name || c.number }}
                           onClose={() => setScheduling(false)} onMade={() => { setScheduling(false); next.reload(); }} />
        </section>
    );
}
