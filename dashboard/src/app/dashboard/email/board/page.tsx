"use client";

import { useEffect, useState, type DragEvent } from "react";
import { Button, Card, Dialog, EmptyState, Input, PhraseInput, Select, Skeleton, Status, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { STAGE_LABEL, type Board, type Lead, type Senders } from "@/lib/email";
import { useApi } from "@/lib/useApi";
import { LEADS } from "@/lib/voice/schedule";
import type { LeadStatus } from "@/lib/voice/types";

function Offers({ lead, onChanged }: { lead: Lead; onChanged: () => void }) {
    const toast = useToast();
    const [how, setHow] = useState("");
    const [agreed, setAgreed] = useState(lead.agreed);
    const set = async (yes: boolean) => {
        try {
            await apiJson(`/api/email/consent/${lead.id}`, { method: "POST", json: { agreed: yes, how: how.trim() } });
            setAgreed(yes);
            setHow("");
            onChanged();
        } catch (e) {
            toast((e as Error).message);
        }
    };
    return (
        <div className="border-t border-line pt-3">
            <span className="text-xs text-stone-500">Offers and news by email</span>
            {agreed ? (
                <div className="flex items-center justify-between gap-3 mt-1">
                    <Status tone="good">Agreed</Status>
                    <Button size="sm" variant="ghost" onClick={() => set(false)}>Stop offers</Button>
                </div>
            ) : (
                <div className="mt-1 space-y-2">
                    <p className="text-[13px] text-stone-600">Not agreed. If they said yes to you, note how; it&apos;s kept as the record.</p>
                    <div className="flex flex-wrap gap-2">
                        <Input aria-label="How they agreed" className="flex-1 min-w-40" maxLength={500} value={how} placeholder="Said yes on our call on 3 Nov" onChange={(e) => setHow(e.target.value)} />
                        <Button size="sm" disabled={how.trim().length < 5} onClick={() => set(true)}>They agreed</Button>
                    </div>
                </div>
            )}
        </div>
    );
}

function LeadDialog({ lead, board, onClose, save, onChanged }: { lead: Lead; board: Board; onClose: () => void; save: (id: string, values: Partial<Lead>) => Promise<void>; onChanged: () => void }) {
    const [tags, setTags] = useState(lead.tags);
    const [owner, setOwner] = useState(lead.assigned_to ?? "");
    return (
        <Dialog open onClose={onClose} title={lead.name || lead.email || lead.phone || "This lead"} description={[lead.phone, lead.email].filter(Boolean).join(" · ")}
                footer={<>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" onClick={() => save(lead.id, { tags, assigned_to: owner }).then(onClose)}>Save</Button>
                </>}>
            <div className="space-y-3">
                <label className="block">
                    <span className="text-xs text-stone-500">Looked after by</span>
                    <Select className="mt-1" value={owner} onChange={(e) => setOwner(e.target.value)}>
                        <option value="">Nobody yet</option>
                        {board.team.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </Select>
                </label>
                <div>
                    <span className="text-xs text-stone-500">Tags</span>
                    <div className="mt-1"><PhraseInput keepCase value={tags} onChange={setTags} label="Tags" placeholder="Add a tag" /></div>
                </div>
                {lead.brief && (
                    <div className="border-t border-line pt-3 text-[13px]">
                        <span className="text-xs text-stone-500">The email agent&apos;s hand-over</span>
                        <dl className="mt-1 space-y-1">
                            {([["Wants", lead.brief.wants], ["Was told", lead.brief.told], ["Next", lead.brief.next]] as const).filter(([, v]) => v).map(([k, v]) => (
                                <div key={k} className="flex gap-2"><dt className="text-stone-500 w-16 shrink-0">{k}</dt><dd>{v}</dd></div>
                            ))}
                        </dl>
                    </div>
                )}
                {lead.email && <Offers lead={lead} onChanged={onChanged} />}
            </div>
        </Dialog>
    );
}

/** Where each lead stands. Stages move forward by themselves; drag a lead, or use its menu on a phone. */
export default function LeadBoardPage() {
    const toast = useToast();
    const senders = useApi<Senders>("/api/email/senders");
    const [botId, setBotId] = useState("");
    const board = useApi<Board>(botId ? `/api/email/board/${botId}` : null);
    const [open, setOpen] = useState<Lead | null>(null);
    const [over, setOver] = useState<string | null>(null);
    const assistants = senders.data?.assistants ?? [];
    useEffect(() => { if (!botId && assistants[0]) setBotId(assistants[0].bot_id); }, [botId, assistants]);

    const save = async (id: string, values: Partial<Lead>) => {
        try {
            await apiJson(`/api/email/board/leads/${id}`, { method: "PUT", json: values });
            await board.reload();
        } catch (e) {
            toast((e as Error).message);
        }
    };
    const drop = (e: DragEvent, stage: string) => {
        e.preventDefault();
        setOver(null);
        const id = e.dataTransfer.getData("text/plain");
        if (id && board.data?.leads.find((l) => l.id === id)?.stage !== stage) void save(id, { stage });
    };

    if (senders.error) return <p className="text-sm text-signal">{senders.error}</p>;
    if (!senders.data) return <Skeleton className="h-64" />;
    if (assistants.length === 0) return <Card className="p-5 text-[13px] text-stone-600">Make an assistant first: its leads show here.</Card>;
    if (board.error) return <p className="text-sm text-signal">{board.error}</p>;
    const b = board.data;
    if (!b) return <Skeleton className="h-64" />;
    const names = Object.fromEntries(b.team.map((t) => [t.id, t.name]));
    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-[13px] text-stone-500">
                    {b.total > b.leads.length ? `The newest ${b.leads.length} of your ${b.total} leads` : "Every lead"}, by where they stand. Stages move forward by themselves after calls, meetings and replies.
                </p>
                {assistants.length > 1 && (
                    <Select aria-label="Assistant" className="w-56" value={botId} onChange={(e) => setBotId(e.target.value)}>
                        {assistants.map((a) => <option key={a.bot_id} value={a.bot_id}>{a.bot_name}</option>)}
                    </Select>
                )}
            </div>
            {b.leads.length === 0 ? <Card><EmptyState title="No leads yet" body="People who call, chat or come in from a lead source show up here." /></Card> : (
                <div className="grid grid-flow-col auto-cols-[minmax(230px,1fr)] lg:auto-cols-[minmax(165px,1fr)] gap-3 overflow-x-auto pb-2">
                    {b.stages.map((stage) => {
                        const leads = b.leads.filter((l) => l.stage === stage);
                        return (
                            <section key={stage} aria-label={STAGE_LABEL[stage]} onDragOver={(e) => { e.preventDefault(); setOver(stage); }} onDragLeave={() => setOver(null)} onDrop={(e) => drop(e, stage)}
                                     className={`rounded-lg border p-2 min-h-40 ${over === stage ? "border-plum bg-white" : "border-line bg-white/60"}`}>
                                <h3 className="text-[13px] font-medium px-1.5 py-1">{STAGE_LABEL[stage]} <span className="text-stone-500 tabular-nums font-normal">{leads.length}</span></h3>
                                <ul className="space-y-2 mt-1">
                                    {leads.map((l) => {
                                        const rated = l.status ? LEADS[l.status as LeadStatus] : null;
                                        return (
                                            <li key={l.id} draggable onDragStart={(e) => e.dataTransfer.setData("text/plain", l.id)} className="rounded-md border border-line bg-white p-2.5 cursor-grab active:cursor-grabbing">
                                                <button type="button" onClick={() => setOpen(l)} className="block w-full text-left text-sm truncate hover:underline">{l.name || l.email || l.phone}</button>
                                                {l.name && <p className="text-xs text-stone-500 truncate">{l.phone || l.email}</p>}
                                                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1.5">
                                                    {rated && <Status tone={rated.tone}>{rated.label}</Status>}
                                                    {l.tags.map((t) => <span key={t} className="text-xs text-stone-600 rounded border border-line px-1.5">{t}</span>)}
                                                </div>
                                                {l.assigned_to && <p className="text-xs text-stone-500 mt-1 truncate">{names[l.assigned_to] ?? "Someone on the team"}</p>}
                                                <Select aria-label={`Move ${l.name || l.email || l.phone} to another stage`} className="mt-2 h-8 text-[13px]" value={stage} onChange={(e) => save(l.id, { stage: e.target.value })}>
                                                    {b.stages.map((s) => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}
                                                </Select>
                                            </li>
                                        );
                                    })}
                                </ul>
                            </section>
                        );
                    })}
                </div>
            )}
            {open && <LeadDialog key={open.id} lead={open} board={b} onClose={() => setOpen(null)} save={save} onChanged={() => { void board.reload(); }} />}
        </div>
    );
}
