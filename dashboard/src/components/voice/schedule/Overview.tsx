"use client";

import { useState, type ReactNode } from "react";
import { Card, EmptyState, Skeleton, Button, cn, useToast } from "@/components/ui";
import { apiSave, useApi } from "@/lib/useApi";
import { formatNumber } from "@/lib/voice/api";
import { formatDay, formatSlot, scheduleChanged } from "@/lib/voice/schedule";
import type { MeetingSummary, ScheduleItem, ScheduleOverview } from "@/lib/voice/types";
import { CallSheet, ItemRow } from "./Calls";
import { MeetingRow, MeetingSheet } from "./Meetings";

function Metric({ label, value, note, className }: { label: string; value: string; note?: string; className?: string }) {
    return (
        <div className={cn("p-5", className)}>
            <p className="text-[13px] text-stone-500">{label}</p>
            <p className="text-[28px] leading-none font-semibold tracking-tight tabular-nums mt-3">{value}</p>
            {note && <p className="text-xs text-stone-500 mt-2">{note}</p>}
        </div>
    );
}

function Group({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
    return (
        <section className="border-t border-line first:border-t-0">
            <div className="px-5 pt-4 pb-1">
                <h3 className="text-sm font-medium">{title}</h3>
                {hint && <p className="text-xs text-stone-500 mt-0.5">{hint}</p>}
            </div>
            <ul>{children}</ul>
        </section>
    );
}

type Entry = { at: string; day: string; tz: string; item?: ScheduleItem; meeting?: MeetingSummary };

export function OverviewPanel({ botId, showBot }: { botId: string; showBot: boolean }) {
    const toast = useToast();
    const data = useApi<ScheduleOverview>(`/api/voice/schedule/overview?bot_id=${encodeURIComponent(botId)}`);
    const [meetingId, setMeetingId] = useState<string | null>(null);
    const [itemId, setItemId] = useState<string | null>(null);
    const [busy, setBusy] = useState<string | null>(null);

    if (data.loading && !data.data) return <div className="space-y-6"><Skeleton className="h-32" /><Skeleton className="h-64" /></div>;
    if (data.error || !data.data) return <p className="text-sm text-signal">Couldn&apos;t load the schedule. {data.error}</p>;
    const o = data.data;
    const s = o.stats;

    const mark = async (m: MeetingSummary, attended: boolean) => {
        setBusy(m.id);
        const res = await apiSave(`/api/voice/schedule/meetings/${m.id}/mark`, "POST", { attended });
        setBusy(null);
        if (!res.ok) return toast(res.message);
        toast(attended ? "Marked as attended" : "Marked as missed");
        data.reload();
        scheduleChanged();
    };

    const entries: Entry[] = [
        ...o.calls.filter((c) => c.local).map((c) => ({ at: c.local!, day: c.local!.slice(0, 10), tz: c.timezone, item: c })),
        ...o.meetings.map((m) => ({ at: m.local, day: m.local.slice(0, 10), tz: m.timezone, meeting: m })),
    ].sort((a, b) => a.at.localeCompare(b.at));
    const days = [...new Set(entries.map((e) => e.day))];
    const approvals = o.meetings.filter((m) => m.status === "requested");
    const reviews = o.calls.filter((c) => c.status === "review");
    const needs = approvals.length + reviews.length + o.people.length + o.to_mark.length + o.missed.length;
    const items = [...o.calls, ...o.people, ...o.missed];

    return (
        <>
            <Card className="grid grid-cols-2 lg:grid-cols-4">
                <Metric label="Call-backs booked" value={formatNumber(s.callbacks.booked)} note={`${formatNumber(s.callbacks.reached)} reached · last 30 days`} />
                <Metric label="Follow-ups made" value={formatNumber(s.follow_ups.made)} note={`${formatNumber(s.follow_ups.answered)} answered`} className="border-l" />
                <Metric label="Meetings asked for" value={formatNumber(s.meetings.requested)}
                        note={`${formatNumber(s.meetings.confirmed)} confirmed · ${formatNumber(s.meetings.attended)} attended`} className="border-t lg:border-t-0 lg:border-l" />
                <Metric label="Hot leads" value={formatNumber(s.leads.hot ?? 0)}
                        note={`${formatNumber(s.leads.warm ?? 0)} warm · ${formatNumber(s.leads.cold ?? 0)} cold`} className="border-t border-l lg:border-t-0" />
            </Card>

            {needs > 0 && (
                <Card className="mt-6">
                    <div className="px-5 pt-5">
                        <h2 className="text-[15px] font-semibold">Needs you</h2>
                    </div>
                    <div className="mt-2">
                        {approvals.length > 0 && (
                            <Group title="Meetings to approve" hint="Callers asked to meet your team. Approve, offer another time, or decline.">
                                {approvals.map((m) => <MeetingRow key={m.id} m={m} onOpen={setMeetingId} showBot={showBot} />)}
                            </Group>
                        )}
                        {reviews.length > 0 && (
                            <Group title="Follow-ups to check" hint="The assistant made these after calls. Approve each, or open it to change what it says.">
                                {reviews.map((c) => <ItemRow key={c.id} item={c} onOpen={setItemId} onChanged={data.reload} showBot={showBot} />)}
                            </Group>
                        )}
                        {o.people.length > 0 && (
                            <Group title="Asked for a person" hint="They want someone from your team to call them.">
                                {o.people.map((c) => <ItemRow key={c.id} item={c} onOpen={setItemId} onChanged={data.reload} showBot={showBot} />)}
                            </Group>
                        )}
                        {o.to_mark.length > 0 && (
                            <Group title="Did these meetings happen?" hint="Someone who missed theirs gets a call to pick another time.">
                                {o.to_mark.map((m) => (
                                    <li key={m.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-5 py-3 border-t border-line first:border-t-0">
                                        <button type="button" onClick={() => setMeetingId(m.id)} className="text-left min-w-0 focus-visible:outline-2 focus-visible:outline-plum rounded">
                                            <span className="block text-sm font-medium truncate">{m.name || m.number}</span>
                                            <span className="block text-xs text-stone-500 mt-0.5">{formatSlot(m.local, m.timezone)}</span>
                                        </button>
                                        <div className="flex gap-2">
                                            <Button size="sm" disabled={busy === m.id} onClick={() => mark(m, true)}>Attended</Button>
                                            <Button size="sm" variant="ghost" disabled={busy === m.id} onClick={() => mark(m, false)}>Missed</Button>
                                        </div>
                                    </li>
                                ))}
                            </Group>
                        )}
                        {o.missed.length > 0 && (
                            <Group title="Couldn't reach" hint="Call-backs nobody answered, after every try. You may want to call them yourself.">
                                {o.missed.map((c) => <ItemRow key={c.id} item={c} onOpen={setItemId} onChanged={data.reload} showBot={showBot} />)}
                            </Group>
                        )}
                    </div>
                </Card>
            )}

            <Card className="mt-6">
                <div className="flex items-baseline justify-between px-5 pt-5 pb-2">
                    <h2 className="text-[15px] font-semibold">Coming up</h2>
                    <span className="text-[13px] text-stone-500">Next 7 days</span>
                </div>
                {!entries.length ? (
                    <EmptyState title="Nothing planned this week"
                                body="Call-backs, follow-ups and meetings the assistant arranges on calls show up here, by day." />
                ) : (
                    days.map((day) => {
                        const rows = entries.filter((e) => e.day === day);
                        return (
                            <section key={day} className="border-t border-line">
                                <h3 className="px-5 pt-3 pb-1 text-xs font-medium text-stone-500 uppercase tracking-wide">{formatDay(day, rows[0].tz)}</h3>
                                <ul>
                                    {rows.map((e) => e.meeting
                                        ? <MeetingRow key={`m${e.meeting.id}`} m={e.meeting} onOpen={setMeetingId} showBot={showBot} />
                                        : <ItemRow key={`c${e.item!.id}`} item={e.item!} onOpen={setItemId} onChanged={data.reload} showBot={showBot} />)}
                                </ul>
                            </section>
                        );
                    })
                )}
            </Card>

            <MeetingSheet id={meetingId} onClose={() => setMeetingId(null)} onChanged={data.reload} />
            <CallSheet id={itemId} items={items} onClose={() => setItemId(null)} onChanged={data.reload} />
        </>
    );
}
