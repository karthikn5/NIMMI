"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, Search } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { downloadCsv } from "@/lib/csv";
import { Button, EmptyState, Input, Skeleton } from "@/components/ui";

type Lead = { id: string; session_id: string; data: Record<string, unknown>; created_at: string };

const when = (iso: string) => new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
const label = (key: string) => key.replace(/[_-]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());
/** A field's value, matching the column name in any letter case ("name" and "Name" are one column). */
const valueOf = (l: Lead, column: string) => {
    const key = Object.keys(l.data || {}).find((k) => k.toLowerCase() === column);
    return key === undefined ? undefined : l.data[key];
};

/** Details visitors gave this assistant's flows and chats, one row per conversation. */
export default function LeadsPanel({ botId, botName }: { botId: string; botName: string }) {
    const [leads, setLeads] = useState<Lead[] | null>(null);
    const [error, setError] = useState(false);
    const [query, setQuery] = useState("");

    const load = useCallback(async () => {
        setError(false);
        try {
            const res = await apiFetch(`/api/bots/${botId}/leads`);
            if (!res.ok) throw new Error();
            setLeads(await res.json());
        } catch {
            setError(true);
            setLeads([]);
        }
    }, [botId]);
    useEffect(() => { load(); }, [load]);

    // Columns: every field collected, most common first.
    const columns = useMemo(() => {
        const counts = new Map<string, number>();
        (leads || []).forEach((l) => Object.keys(l.data || {}).forEach((k) => counts.set(k.toLowerCase(), (counts.get(k.toLowerCase()) || 0) + 1)));
        return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k);
    }, [leads]);

    const rows = useMemo(() => {
        const q = query.trim().toLowerCase();
        if (!q) return leads || [];
        return (leads || []).filter((l) => Object.values(l.data || {}).some((v) => String(v).toLowerCase().includes(q)));
    }, [leads, query]);

    const exportCsv = () => downloadCsv(`${(botName || "assistant").replace(/\W+/g, "-").toLowerCase()}-leads.csv`,
        ["Date", ...columns.map(label)],
        rows.map((l) => [new Date(l.created_at).toISOString(), ...columns.map((c) => valueOf(l, c) ?? "")]));

    return (
        <div className="max-w-6xl mx-auto px-4 sm:px-8 py-8">
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-6">
                <div>
                    <h1 className="text-lg font-semibold text-ink">Leads</h1>
                    <p className="text-[13px] text-stone-500 mt-0.5">Details visitors shared with {botName || "this assistant"}, from its flow and chats.</p>
                </div>
                <div className="flex gap-2">
                    <div className="relative">
                        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-stone-400" aria-hidden />
                        <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search leads" className="pl-8 w-56" aria-label="Search leads" />
                    </div>
                    <Button onClick={exportCsv} disabled={!rows.length}><Download size={14} /> Export CSV</Button>
                </div>
            </div>

            <div className="bg-white border border-line rounded-lg overflow-hidden">
                {leads === null ? (
                    <div className="p-5 space-y-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-9" />)}</div>
                ) : error ? (
                    <EmptyState title="Couldn't load leads" body="Check your connection and try again." action={<Button size="sm" onClick={load}>Try again</Button>} />
                ) : !leads.length ? (
                    <EmptyState title="No leads yet" body="When visitors answer questions in your flow, or share their name, phone or email in chat, they appear here." />
                ) : !rows.length ? (
                    <EmptyState title="No matches" body={`Nothing matches “${query}”.`} />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-[13px]">
                            <thead>
                                <tr className="border-b border-line bg-stone-50/70 text-stone-500">
                                    <th className="px-4 py-2.5 font-medium whitespace-nowrap">Date</th>
                                    {columns.map((c) => <th key={c} className="px-4 py-2.5 font-medium whitespace-nowrap">{label(c)}</th>)}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-line">
                                {rows.map((l) => (
                                    <tr key={l.id} className="hover:bg-stone-50/60">
                                        <td className="px-4 py-3 text-stone-500 whitespace-nowrap tabular-nums">{when(l.created_at)}</td>
                                        {columns.map((c) => (
                                            <td key={c} className="px-4 py-3 text-ink max-w-[260px] truncate">{valueOf(l, c) !== undefined && valueOf(l, c) !== "" ? String(valueOf(l, c)) : <span className="text-stone-300">–</span>}</td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
            {!!leads?.length && <p className="text-[12px] text-stone-500 mt-3">{rows.length} of {leads.length} {leads.length === 1 ? "lead" : "leads"}</p>}
        </div>
    );
}
