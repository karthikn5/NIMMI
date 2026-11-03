"use client";

import { useEffect, type ReactNode } from "react";
import Link from "next/link";
import { Card, EmptyState, Skeleton } from "@/components/ui";
import { LeadLine } from "@/components/leads/LeadLine";
import { PROMISE_KIND, dueInline, formatDue, type LeadRow, type Queues } from "@/lib/leads";
import { useApi } from "@/lib/useApi";
import { formatWhen } from "@/lib/voice/api";

function Queue({ title, about, count, children }: { title: string; about: string; count: number; children: ReactNode }) {
    if (!count) return null;
    return (
        <Card>
            <div className="px-5 pt-4 pb-3 border-b border-line">
                <h2 className="text-sm font-medium">{title} <span className="text-stone-500 font-normal tabular-nums">{count}</span></h2>
                <p className="text-[13px] text-stone-500 mt-0.5">{about}</p>
            </div>
            <ul>{children}</ul>
        </Card>
    );
}

const lines = (rows: LeadRow[], showBot: boolean) => rows.map((l) => <LeadLine key={l.id} lead={l} showBot={showBot} />);

export default function NeedsAttentionPage() {
    const q = useApi<Queues>("/api/crm/queues");
    const { reload } = q;
    useEffect(() => {  // new leads come in by themselves
        const t = setInterval(() => { void reload(); }, 30_000);
        return () => clearInterval(t);
    }, [reload]);
    if (q.error) return <p className="text-sm text-signal">{q.error}</p>;
    if (!q.data) return <Skeleton className="h-64" />;
    const d = q.data;
    const bots = new Set([...d.overdue, ...d.today, ...d.new, ...d.no_next].map((l) => l.bot_id));
    const many = bots.size > 1;
    const owed = d.promises ?? [];  // phase 7: missing while an older backend answers
    const empty = !(d.overdue.length || d.today.length || d.new.length || d.no_next.length || d.asked_for_person.length || d.meetings.length || owed.length);
    if (empty) return <Card><EmptyState title="Nothing needs you right now" body={<>New leads, due tasks, promises and people waiting show up here. <Link href="/dashboard/leads/all" className="text-plum hover:underline">See all leads</Link>.</>} /></Card>;
    return (
        <div className="space-y-5">
            <Queue title="Overdue" about="Tasks past their time." count={d.overdue.length}>{lines(d.overdue, many)}</Queue>
            <Queue title="Promises due" about="What your assistant or your team told them would be done, with nothing yet to show it was." count={owed.length}>
                {owed.map((p) => (
                    <li key={p.id} className="border-t border-line first:border-t-0">
                        <Link href={`/dashboard/leads/${p.lead.id}`} className="block px-5 py-3 hover:bg-paper/70">
                            <span className="block text-sm truncate">{p.what} <span className="text-stone-500">· {p.lead.name || p.lead.phone || p.lead.email}</span></span>
                            <span className={`block text-[13px] truncate ${p.late ? "text-signal" : "text-stone-500"}`}>
                                {[PROMISE_KIND[p.kind] ?? p.kind, `${p.late ? "late, " : ""}${p.due_said ? "due" : "expected by"} ${dueInline(p.due_at)}`, p.lead.owner].filter(Boolean).join(" · ")}
                            </span>
                        </Link>
                    </li>
                ))}
            </Queue>
            <Queue title="Asked for a person" about="They want to talk to someone on your team." count={d.asked_for_person.length}>
                {d.asked_for_person.map((a) => (
                    <li key={a.id} className="border-t border-line first:border-t-0">
                        <Link href={`/dashboard/voice/schedule?tab=calls&item=${a.id}`} className="block px-5 py-3 hover:bg-paper/70">
                            <span className="block text-sm truncate">{a.name || a.phone}</span>
                            <span className="block text-[13px] text-stone-500 truncate">{[a.name ? a.phone : null, a.about, a.at ? formatWhen(a.at) : null].filter(Boolean).join(" · ")}</span>
                        </Link>
                    </li>
                ))}
            </Queue>
            <Queue title="Due today" about="What's coming up." count={d.today.length}>{lines(d.today, many)}</Queue>
            <Queue title="New, nobody looks after them" about="Give each one to someone." count={d.new.length}>{lines(d.new, many)}</Queue>
            <Queue title="Meetings to approve" about="Approve, offer another time, or decline." count={d.meetings.length}>
                {d.meetings.map((m) => (
                    <li key={m.id} className="border-t border-line first:border-t-0">
                        <Link href={`/dashboard/voice/schedule?tab=meetings&meeting=${m.id}`} className="block px-5 py-3 hover:bg-paper/70">
                            <span className="block text-sm truncate">{m.name || m.phone}</span>
                            <span className="block text-[13px] text-stone-500 truncate">{[m.starts_at ? formatDue(m.starts_at) : null, m.about].filter(Boolean).join(" · ")}</span>
                        </Link>
                    </li>
                ))}
            </Queue>
            <Queue title="No next step" about="An open lead with nothing planned. Plan something, or close it." count={d.no_next.length}>{lines(d.no_next, many)}</Queue>
        </div>
    );
}
