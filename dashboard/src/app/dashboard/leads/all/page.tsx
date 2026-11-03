"use client";

import { useEffect, useState } from "react";
import { Plus, Search } from "lucide-react";
import { Button, Card, EmptyState, Input, Select, Skeleton, useToast } from "@/components/ui";
import { AddLead } from "@/components/leads/AddLead";
import { ImportLeads } from "@/components/leads/ImportLeads";
import { LeadLine } from "@/components/leads/LeadLine";
import { apiFetch } from "@/lib/api";
import { STAGES, sourceLabel, type LeadList } from "@/lib/leads";
import { useApi } from "@/lib/useApi";
import { useRole } from "@/lib/whatsapp";

const PAGE = 50;

export default function AllLeadsPage() {
    const toast = useToast();
    const role = useRole();
    const [q, setQ] = useState("");
    const [typed, setTyped] = useState("");
    const [stage, setStage] = useState("");
    const [owner, setOwner] = useState("");
    const [source, setSource] = useState("");
    const [botId, setBotId] = useState("");
    const [due, setDue] = useState("");
    const [offset, setOffset] = useState(0);
    const [adding, setAdding] = useState(false);
    const [importing, setImporting] = useState(false);
    const [quality, setQuality] = useState("");
    useEffect(() => {
        const t = setTimeout(() => { setTyped(q); setOffset(0); }, 300);
        return () => clearTimeout(t);
    }, [q]);
    const query = new URLSearchParams(Object.entries({ q: typed, stage, owner, source, bot_id: botId, due, quality }).filter(([, v]) => v));
    const list = useApi<LeadList>(`/api/crm/leads?${query}&offset=${offset}&limit=${PAGE}`);
    const d = list.data;
    const pick = (set: (v: string) => void) => (e: { target: { value: string } }) => { set(e.target.value); setOffset(0); };
    const exportCsv = async () => {
        try {
            const res = await apiFetch(`/api/crm/leads/export?${query}`);
            if (!res.ok) throw new Error("Couldn't make the file");
            const url = URL.createObjectURL(await res.blob());
            const a = document.createElement("a");
            a.href = url;
            a.download = "nimmi-leads.csv";
            a.click();
            URL.revokeObjectURL(url);
        } catch (e) {
            toast((e as Error).message);
        }
    };
    const manager = !!role && role !== "agent";
    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
                <div className="relative flex-1 min-w-52">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" aria-hidden />
                    <Input aria-label="Search" className="pl-8" placeholder="Name, number or email" value={q} onChange={(e) => setQ(e.target.value)} />
                </div>
                {manager && <Button onClick={() => setImporting(true)}>Import</Button>}
                {manager && <Button onClick={exportCsv}>Export</Button>}
                {manager && <Button variant="primary" onClick={() => setAdding(true)}><Plus size={14} aria-hidden /> Add lead</Button>}
            </div>
            <div className="flex flex-wrap gap-2">
                <Select aria-label="Stage" className="w-40" value={stage} onChange={pick(setStage)}>
                    <option value="">Every stage</option>
                    {(d?.stages ?? Object.keys(STAGES)).map((s) => <option key={s} value={s}>{STAGES[s] ?? s}</option>)}
                </Select>
                <Select aria-label="Looked after by" className="w-44" value={owner} onChange={pick(setOwner)}>
                    <option value="">Anyone</option>
                    <option value="me">Me</option>
                    {manager && <option value="nobody">Nobody yet</option>}
                    {manager && d?.team.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </Select>
                <Select aria-label="Source" className="w-44" value={source} onChange={pick(setSource)}>
                    <option value="">Every source</option>
                    {d?.sources.map((s) => <option key={s} value={s}>{sourceLabel(s)}</option>)}
                </Select>
                <Select aria-label="Next step" className="w-40" value={due} onChange={pick(setDue)}>
                    <option value="">Any next step</option>
                    <option value="overdue">Overdue</option>
                    <option value="none">No next step</option>
                </Select>
                {(manager && (d?.junk ?? 0) > 0 || quality) && (
                    <Select aria-label="Show" className="w-44" value={quality} onChange={pick(setQuality)}>
                        <option value="">Real leads</option>
                        <option value="junk">Marked as junk ({d?.junk ?? 0})</option>
                    </Select>
                )}
                {(d?.bots.length ?? 0) > 1 && (
                    <Select aria-label="Assistant" className="w-48" value={botId} onChange={pick(setBotId)}>
                        <option value="">Every assistant</option>
                        {d?.bots.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                    </Select>
                )}
            </div>
            {list.error ? <p className="text-sm text-signal">{list.error}</p> : !d ? <Skeleton className="h-64" /> : d.items.length === 0 ? (
                <Card><EmptyState title="No leads here" body={typed || stage || owner || source || due ? "Nothing matches. Try fewer filters." : "People who call, chat or come in from a source show up here."} /></Card>
            ) : (
                <>
                    <Card><ul>{d.items.map((l) => <LeadLine key={l.id} lead={l} showBot={d.bots.length > 1} />)}</ul></Card>
                    <div className="flex items-center justify-between text-[13px] text-stone-500">
                        <span>{d.total === 1 ? "1 lead" : `${offset + 1} to ${Math.min(offset + PAGE, d.total)} of ${d.total} leads`}</span>
                        <span className="flex gap-2">
                            <Button size="sm" variant="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(offset - PAGE, 0))}>Newer</Button>
                            <Button size="sm" variant="ghost" disabled={offset + PAGE >= d.total} onClick={() => setOffset(offset + PAGE)}>Older</Button>
                        </span>
                    </div>
                </>
            )}
            {d && <AddLead open={adding} onClose={() => setAdding(false)} bots={d.bots} />}
            {d && importing && <ImportLeads bots={d.bots} onClose={() => setImporting(false)} onDone={() => { void list.reload(); }} />}
        </div>
    );
}
