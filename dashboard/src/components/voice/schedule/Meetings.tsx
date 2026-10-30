"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronRight, MapPin, Phone, Video } from "lucide-react";
import {
    Button, Card, Dialog, EmptyState, Input, Segmented, Select, Sheet, Skeleton, Status, Switch, Textarea, cn, useToast,
} from "@/components/ui";
import { apiSave, useApi } from "@/lib/useApi";
import { formatWhen } from "@/lib/voice/api";
import { ITEM_STATUS, MEETING_KINDS, MEETING_STATUS, formatClock, formatSlot, scheduleChanged, todayIn } from "@/lib/voice/schedule";
import type { MeetingDetail, MeetingKind, MeetingSummary, ScheduleHost } from "@/lib/voice/types";

const KIND_ICON: Record<MeetingKind, typeof Video> = { online: Video, in_person: MapPin, phone: Phone };

type View = "requests" | "upcoming" | "past";
const EMPTY: Record<View, { title: string; body: string }> = {
    requests: { title: "No requests waiting", body: "When a caller asks to meet your team, the request waits here for your OK." },
    upcoming: { title: "No meetings coming up", body: "Approved meetings show here, with how each person joins." },
    past: { title: "No past meetings yet", body: "Meetings move here once their time has passed." },
};

export function MeetingRow({ m, onOpen, showBot }: { m: MeetingSummary; onOpen: (id: string) => void; showBot?: boolean }) {
    const Icon = KIND_ICON[m.kind];
    return (
        <li>
            <button
                type="button"
                onClick={() => onOpen(m.id)}
                className="w-full grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[9.5rem_minmax(0,1fr)_11rem_16px] items-center gap-x-4 gap-y-1 px-5 py-3 border-t border-line first:border-t-0 text-left hover:bg-stone-50 transition-colors focus-visible:outline-2 focus-visible:outline-plum focus-visible:-outline-offset-2"
            >
                <span className="hidden sm:block text-[13px] tabular-nums">{formatSlot(m.local, m.timezone)}</span>
                <span className="min-w-0">
                    <span className="flex items-center gap-1.5 text-sm font-medium">
                        <Icon size={13} className="text-stone-400 shrink-0" aria-label={MEETING_KINDS[m.kind]} />
                        <span className="truncate">{m.name || m.number}</span>
                    </span>
                    <span className="block text-xs text-stone-500 truncate mt-0.5">
                        <span className="sm:hidden tabular-nums">{formatSlot(m.local, m.timezone)} · </span>
                        {[m.topic || `${MEETING_KINDS[m.kind]} meeting`, showBot && m.bot_name].filter(Boolean).join(" · ")}
                    </span>
                </span>
                <Status tone={MEETING_STATUS[m.status].tone}>{MEETING_STATUS[m.status].label}</Status>
                <ChevronRight size={16} className="hidden sm:block text-stone-300" aria-hidden />
            </button>
        </li>
    );
}

export function MeetingsPanel({ botId, showBot, openId, onOpen }: {
    botId: string; showBot: boolean; openId: string | null; onOpen: (id: string | null) => void;
}) {
    const [view, setView] = useState<View>("requests");
    const list = useApi<MeetingSummary[]>(`/api/voice/schedule/meetings?status=${view}&bot_id=${encodeURIComponent(botId)}`);

    return (
        <>
            <div className="mb-4">
                <Segmented label="Show" value={view} onChange={setView} options={[
                    { value: "requests", label: "Requests" }, { value: "upcoming", label: "Upcoming" }, { value: "past", label: "Past" },
                ]} />
            </div>
            <Card>
                {list.loading ? (
                    <div className="p-5 space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-11" />)}</div>
                ) : list.error ? (
                    <p className="p-5 text-sm text-signal">Couldn&apos;t load meetings. {list.error}</p>
                ) : !list.data?.length ? (
                    <EmptyState title={EMPTY[view].title} body={EMPTY[view].body} />
                ) : (
                    <ul>{list.data.map((m) => <MeetingRow key={m.id} m={m} onOpen={onOpen} showBot={showBot} />)}</ul>
                )}
            </Card>
            <MeetingSheet id={openId} onClose={() => onOpen(null)} onChanged={list.reload} />
        </>
    );
}

const MESSAGE_LABELS: Record<string, string> = {
    meeting_confirmed: "Confirmation sent to them",
    meeting_day_before: "Day-before reminder sent",
    meeting_link: "Joining details sent",
    meeting_cancelled: "Told them it's cancelled",
    meeting_team_requested: "Team emailed about the request",
    meeting_team_confirmed: "Calendar invite emailed to the host",
    meeting_team_starting: "Host reminded",
    meeting_team_cancelled: "Team told they cancelled",
};
const CALL_LABELS: Record<string, string> = {
    confirmed: "Call to confirm it", proposed: "Call to offer the other time", declined: "Call to find another time", missed: "Call after they missed it",
};

type Event = { at: string; text: string; note?: string | null; tone?: "good" | "warn" | "bad" | "neutral"; href?: string };

function timeline(m: MeetingDetail): Event[] {
    const events: Event[] = m.history.map((h) => ({ at: h.at, text: h.what }));
    for (const msg of m.messages) {
        if (!msg.at) continue;
        const via = msg.kind.startsWith("meeting_team_") ? undefined : m.sent[msg.kind.slice("meeting_".length)]?.via;
        events.push({
            at: msg.at, text: MESSAGE_LABELS[msg.kind] ?? msg.kind,
            note: msg.status === "sent" ? (via?.length ? `By ${via.map((v) => (v === "whatsapp" ? "WhatsApp" : "email")).join(" and ")}` : null) : msg.note,
            tone: msg.status === "sent" ? "good" : msg.status === "failed" ? "bad" : "warn",
        });
    }
    for (const c of m.calls) {
        if (!c.due_at) continue;
        events.push({
            at: c.due_at, text: `${CALL_LABELS[c.about ?? ""] ?? "Call"}: ${ITEM_STATUS[c.status].label.toLowerCase()}`,
            note: c.status === "done" || c.status === "cancelled" || c.status === "failed" ? c.last_error : null,
            tone: ITEM_STATUS[c.status].tone === "plum" ? "neutral" : ITEM_STATUS[c.status].tone as Event["tone"],
            href: c.call_id ? `/dashboard/voice/calls?call=${c.call_id}` : undefined,
        });
    }
    return events.sort((a, b) => b.at.localeCompare(a.at));
}

export function MeetingSheet({ id, onClose, onChanged }: { id: string | null; onClose: () => void; onChanged: () => void }) {
    const toast = useToast();
    const meeting = useApi<MeetingDetail>(id ? `/api/voice/schedule/meetings/${id}` : null);
    const hosts = useApi<ScheduleHost[]>(id ? "/api/voice/schedule/hosts" : null);
    const [dialog, setDialog] = useState<null | "approve" | "time" | "decline">(null);
    const [notes, setNotes] = useState("");
    const [busy, setBusy] = useState(false);
    const m = id ? meeting.data : null;

    useEffect(() => { if (meeting.data) setNotes(meeting.data.notes); }, [meeting.data]);

    const act = async (path: string, method: "POST" | "PATCH", body: unknown, done: string) => {
        setBusy(true);
        const res = await apiSave(`/api/voice/schedule/meetings/${id}${path}`, method, body);
        setBusy(false);
        if (!res.ok) {
            toast(res.message);
            return false;
        }
        meeting.setData(res.data as MeetingDetail);
        onChanged();
        scheduleChanged();
        toast(done);
        return true;
    };

    const started = m ? new Date(m.starts_at).getTime() <= Date.now() : false;
    const waiting = m && (m.status === "requested" || m.status === "proposed");
    const host = hosts.data?.find((h) => h.id === m?.host_id);

    return (
        <Sheet open={!!id} onClose={onClose} title={m ? (m.name || m.number) : "Meeting"}
               subtitle={m ? `${formatSlot(m.local, m.timezone)} · ${MEETING_KINDS[m.kind]} · ${m.minutes} min` : undefined}>
            {!m ? (
                <div className="p-6 space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}</div>
            ) : (
                <div className="px-6 py-5 space-y-6">
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                        <Status tone={MEETING_STATUS[m.status].tone}>{MEETING_STATUS[m.status].label}</Status>
                        <a href={`tel:${m.number.replace(/\s/g, "")}`} className="text-[13px] text-plum hover:underline underline-offset-4 tabular-nums">{m.number}</a>
                        <span className="text-[13px] text-stone-500">{m.bot_name}</span>
                    </div>

                    {waiting && (
                        <div className="flex flex-wrap gap-2">
                            <Button variant="primary" size="sm" onClick={() => setDialog("approve")} disabled={busy}>Approve</Button>
                            <Button size="sm" onClick={() => setDialog("time")} disabled={busy}>Offer another time</Button>
                            <Button size="sm" variant="ghost" onClick={() => setDialog("decline")} disabled={busy}>Decline</Button>
                        </div>
                    )}
                    {m.status === "confirmed" && !started && (
                        <div className="flex flex-wrap gap-2">
                            <Button size="sm" onClick={() => setDialog("time")} disabled={busy}>Move it</Button>
                            <Button size="sm" variant="ghost" onClick={() => setDialog("decline")} disabled={busy}>Cancel the meeting</Button>
                        </div>
                    )}
                    {started && ["confirmed", "done", "no_show"].includes(m.status) && (
                        <div>
                            <p className="text-[13px] text-stone-600 mb-2">{m.status === "confirmed" ? "Did it happen?" : "Change what happened:"}</p>
                            <div className="flex flex-wrap gap-2">
                                {m.status !== "done" && <Button size="sm" variant={m.status === "confirmed" ? "primary" : "secondary"} disabled={busy}
                                                                onClick={() => act("/mark", "POST", { attended: true }, "Marked as attended")}>They attended</Button>}
                                {m.status !== "no_show" && <Button size="sm" disabled={busy}
                                                                   onClick={() => act("/mark", "POST", { attended: false }, "Marked as missed")}>They didn&apos;t join</Button>}
                            </div>
                        </div>
                    )}

                    <dl className="grid grid-cols-[minmax(0,8.5rem)_1fr] gap-x-4 gap-y-2.5 text-[13px]">
                        <dt className="text-stone-500">About</dt>
                        <dd className="text-ink">{m.topic || "Not said"}</dd>
                        <dt className="text-stone-500">{m.kind === "online" ? "Link" : m.kind === "in_person" ? "Where" : "How"}</dt>
                        <dd className="text-ink break-all">
                            {m.kind === "phone" ? "Your team calls them" : m.place || <span className="text-signal">Not set yet</span>}
                            {m.kind !== "phone" && !m.link && m.place && <span className="text-stone-500"> (the default)</span>}
                        </dd>
                        <dt className="text-stone-500">Host</dt>
                        <dd>{host ? host.name : "Not chosen"}</dd>
                        <dt className="text-stone-500">Writing to them</dt>
                        <dd className="text-stone-700">
                            {[m.channels.whatsapp === "window" ? "WhatsApp (they chatted in the last 24 hours)" : m.channels.whatsapp === "template" ? "WhatsApp (your template)" : null,
                              m.channels.email ? `Email (${m.email})` : null].filter(Boolean).join(", ") ||
                                <span className="text-amber-700">No way to write to them yet: add their email, or a WhatsApp template in Settings</span>}
                        </dd>
                        {m.source_call && (
                            <>
                                <dt className="text-stone-500">Asked for on</dt>
                                <dd>
                                    <Link href={`/dashboard/voice/calls?call=${m.source_call.id}`} className="text-plum hover:underline underline-offset-4">
                                        {m.source_call.started_at ? formatWhen(m.source_call.started_at) : "a call"}
                                    </Link>
                                    {m.source_call.summary && <span className="block text-stone-600 mt-0.5 leading-relaxed">{m.source_call.summary}</span>}
                                </dd>
                            </>
                        )}
                    </dl>

                    <section>
                        <label htmlFor="m-notes" className="text-sm font-medium">Notes for the team</label>
                        <Textarea id="m-notes" className="mt-2" rows={3} maxLength={2000} value={notes}
                                  placeholder="e.g. Wants the weekend batch. Bring the fee sheet." onChange={(e) => setNotes(e.target.value)} />
                        <div className="flex justify-end mt-2">
                            <Button size="sm" variant="primary" disabled={busy || notes === m.notes}
                                    onClick={() => act("", "PATCH", { notes }, "Saved")}>Save notes</Button>
                        </div>
                    </section>

                    <section>
                        <h3 className="text-sm font-medium">What happened</h3>
                        <ol className="mt-2 space-y-2.5">
                            {timeline(m).map((e, i) => (
                                <li key={i} className="grid grid-cols-[7.5rem_minmax(0,1fr)] gap-3 text-[13px]">
                                    <span className="text-stone-500 tabular-nums">{formatWhen(e.at)}</span>
                                    <span>
                                        {e.tone ? <Status tone={e.tone}>{e.href ? <Link href={e.href} className="hover:underline underline-offset-4">{e.text}</Link> : e.text}</Status> : e.text}
                                        {e.note && <span className="block text-xs text-stone-500 mt-0.5">{e.note}</span>}
                                    </span>
                                </li>
                            ))}
                        </ol>
                    </section>
                </div>
            )}
            {m && (
                <>
                    <ApproveDialog open={dialog === "approve"} meeting={m} hosts={hosts.data ?? []} busy={busy} onClose={() => setDialog(null)}
                                   onApprove={async (body) => { if (await act("/approve", "POST", body, "Approved")) setDialog(null); }} />
                    <TimeDialog open={dialog === "time"} meeting={m} busy={busy} onClose={() => setDialog(null)}
                                onPick={async (body) => {
                                    if (await act("/propose", "POST", body, m.status === "confirmed" ? "Moved. They'll get a call with the new time." : "Offered. The assistant will call them to ask."))
                                        setDialog(null);
                                }} />
                    <DeclineDialog open={dialog === "decline"} meeting={m} busy={busy} onClose={() => setDialog(null)}
                                   onDecline={async (body) => { if (await act("/decline", "POST", body, "Done")) setDialog(null); }} />
                </>
            )}
        </Sheet>
    );
}

function ApproveDialog({ open, meeting: m, hosts, busy, onClose, onApprove }: {
    open: boolean; meeting: MeetingDetail; hosts: ScheduleHost[]; busy: boolean; onClose: () => void;
    onApprove: (body: { link: string; host_id: string | null }) => void;
}) {
    const [link, setLink] = useState("");
    const [host, setHost] = useState("");
    useEffect(() => { if (open) { setLink(m.link); setHost(m.host_id ?? ""); } }, [open, m.link, m.host_id]);
    const needsLink = m.kind === "online" && !m.setup.default_link && !link.trim();
    const writes = [m.channels.whatsapp ? "WhatsApp" : null, m.channels.email ? "email" : null].filter(Boolean).join(" and ");

    return (
        <Dialog open={open} onClose={onClose} title="Approve this meeting"
                description={`${formatSlot(m.local, m.timezone)}, ${MEETING_KINDS[m.kind].toLowerCase()}, with ${m.name || m.number}.`}
                footer={<>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" disabled={busy || needsLink} onClick={() => onApprove({ link: link.trim(), host_id: host || null })}>
                        {busy ? "Approving…" : "Approve"}
                    </Button>
                </>}>
            <div className="space-y-4">
                {m.kind !== "phone" && (
                    <div>
                        <label htmlFor="ap-link" className="text-[13px] text-stone-600">{m.kind === "online" ? "Meeting link" : "Address"}</label>
                        <Input id="ap-link" className="mt-1" value={link} maxLength={500} onChange={(e) => setLink(e.target.value)}
                               placeholder={(m.kind === "online" ? m.setup.default_link : m.setup.address) || (m.kind === "online" ? "https://meet.google.com/…" : "")} />
                        <p className="text-xs text-stone-500 mt-1">
                            {m.kind === "online" && !m.setup.default_link ? "Needed: they get it before the meeting." : "Leave empty to use your default from Settings."}
                        </p>
                    </div>
                )}
                {hosts.length > 0 && (
                    <div>
                        <label htmlFor="ap-host" className="text-[13px] text-stone-600">Who takes it</label>
                        <Select id="ap-host" className="mt-1" value={host} onChange={(e) => setHost(e.target.value)}>
                            <option value="">Not chosen</option>
                            {hosts.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}
                        </Select>
                        <p className="text-xs text-stone-500 mt-1">They get a calendar invite by email, and a reminder before it starts.</p>
                    </div>
                )}
                <p className="text-[13px] text-stone-600 leading-relaxed">
                    {m.setup.confirm_call ? "The assistant calls them to confirm it" : "No confirmation call (it's off in Settings)"}
                    {writes ? `, and writes to them on ${writes}` : ""}.
                    {m.kind === "online" && ` The link goes out ${m.setup.link_minutes} minutes before it starts.`}
                </p>
            </div>
        </Dialog>
    );
}

function TimeDialog({ open, meeting: m, busy, onClose, onPick }: {
    open: boolean; meeting: MeetingDetail; busy: boolean; onClose: () => void; onPick: (body: { date: string; time: string }) => void;
}) {
    const [day, setDay] = useState("");
    const [time, setTime] = useState("");
    const free = useApi<{ date: string; times: string[] }[]>(open && day ? `/api/voice/schedule/free-times?bot_id=${m.bot_id}&date=${day}` : null);
    useEffect(() => { if (open) { setDay(m.local.slice(0, 10)); setTime(""); } }, [open, m.local]);
    const times = free.data?.find((d) => d.date === day)?.times ?? [];
    const moving = m.status === "confirmed";

    return (
        <Dialog open={open} onClose={onClose} title={moving ? "Move the meeting" : "Offer another time"}
                description={moving ? "They get a call with the new time, and a new confirmation." : "The assistant calls them to ask whether it works."}
                footer={<>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" disabled={busy || !day || !time} onClick={() => onPick({ date: day, time })}>
                        {busy ? "Saving…" : moving ? "Move" : "Offer this time"}
                    </Button>
                </>}>
            <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label htmlFor="t-day" className="text-[13px] text-stone-600">Day</label>
                        <Input id="t-day" type="date" className="mt-1" min={todayIn(m.timezone)} value={day} onChange={(e) => { setDay(e.target.value); setTime(""); }} />
                    </div>
                    <div>
                        <label htmlFor="t-time" className="text-[13px] text-stone-600">Time</label>
                        <Input id="t-time" type="time" className="mt-1 tabular-nums" value={time} onChange={(e) => setTime(e.target.value)} />
                    </div>
                </div>
                <div>
                    <p className="text-[13px] text-stone-600">Free that day</p>
                    {free.loading ? <Skeleton className="h-8 mt-2" /> : times.length === 0 ? (
                        <p className="text-xs text-stone-500 mt-1">Nothing free in your meeting hours. You can still type a time.</p>
                    ) : (
                        <div className="flex flex-wrap gap-1.5 mt-2">
                            {times.map((t) => (
                                <button key={t} type="button" onClick={() => setTime(t)} aria-pressed={time === t}
                                        className={cn("h-7 px-2.5 rounded-md border text-[13px] tabular-nums transition-colors focus-visible:outline-2 focus-visible:outline-plum",
                                            time === t ? "border-plum bg-plum text-white" : "border-line-strong bg-white hover:bg-stone-50")}>
                                    {formatClock(t)}
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </Dialog>
    );
}

function DeclineDialog({ open, meeting: m, busy, onClose, onDecline }: {
    open: boolean; meeting: MeetingDetail; busy: boolean; onClose: () => void; onDecline: (body: { call: boolean; reason: string }) => void;
}) {
    const [call, setCall] = useState(true);
    const [reason, setReason] = useState("");
    useEffect(() => { if (open) { setCall(true); setReason(""); } }, [open]);
    const confirmed = m.status === "confirmed";

    return (
        <Dialog open={open} onClose={onClose} title={confirmed ? "Cancel this meeting?" : "Decline this request?"}
                footer={<>
                    <Button variant="ghost" onClick={onClose}>Keep it</Button>
                    <Button variant="danger" disabled={busy} onClick={() => onDecline({ call, reason: reason.trim() })}>
                        {confirmed ? "Cancel meeting" : "Decline"}
                    </Button>
                </>}>
            <div className="space-y-4">
                <label className="flex items-start gap-3">
                    <Switch checked={call} onChange={setCall} label="Call them to find another time" />
                    <span className="text-sm">
                        Call them to find another time
                        <span className="block text-[13px] text-stone-500 mt-0.5">
                            {call ? "The assistant explains and offers your free times." : "They're told in writing instead, where possible."}
                        </span>
                    </span>
                </label>
                <div>
                    <label htmlFor="d-reason" className="text-[13px] text-stone-600">Note for your team (optional)</label>
                    <Textarea id="d-reason" className="mt-1" rows={2} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
                </div>
            </div>
        </Dialog>
    );
}
