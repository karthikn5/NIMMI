"use client";

import { useEffect, useState } from "react";
import { Button, Card, Dialog, Input, Select, Skeleton, Status, Textarea, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { MADE_ON, PROMISE_KIND, dueInline, localInput, type LeadDetail, type LeadPromise, type PromiseEvidence, type PromiseKind } from "@/lib/leads";
import { formatWhen } from "@/lib/voice/api";

const HOW: Record<string, string> = { call: "Called them", whatsapp: "On WhatsApp", email: "By email", visit: "In person", other: "Other" };

/** What the business promised this person (backend leads/promises.py). Each stays open until a record shows it was done: never just ticked off. */
export function Promises({ lead, onChanged }: { lead: LeadDetail; onChanged: () => void }) {
    const [adding, setAdding] = useState(false);
    const [keeping, setKeeping] = useState<LeadPromise | null>(null);
    const [cancelling, setCancelling] = useState<LeadPromise | null>(null);
    if (lead.promises === undefined) return null;  // an older server: nothing to show yet
    const list = lead.promises;
    const open = list.filter((p) => p.status === "open");
    return (
        <Card>
            <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4 pb-3">
                <div className="min-w-0">
                    <h3 className="text-sm font-medium">Promises</h3>
                    <p className="text-[13px] text-stone-500 mt-0.5">
                        What your assistant or your team said would be done for them. Each stays open until something shows it was done.
                    </p>
                </div>
                <Button size="sm" onClick={() => setAdding(true)}>Add a promise</Button>
            </div>
            {list.length === 0 ? (
                <p className="px-5 pb-4 text-[13px] text-stone-500">Nothing promised yet.</p>
            ) : (
                <ul className="border-t border-line">
                    {list.map((p) => <PromiseRow key={p.id} p={p} onKeep={() => setKeeping(p)} onCancel={() => setCancelling(p)} />)}
                </ul>
            )}
            {!!open.length && open.some((p) => p.late) && (
                <p className="px-5 py-2.5 border-t border-line text-xs text-stone-500">A late promise is on Needs attention until it&apos;s kept or cancelled.</p>
            )}
            {adding && <AddPromise lead={lead} onClose={() => setAdding(false)} onDone={() => { setAdding(false); onChanged(); }} />}
            {keeping && <KeepPromise p={keeping} how={lead.promise_how ?? HOW} onClose={() => setKeeping(null)} onDone={() => { setKeeping(null); onChanged(); }} />}
            {cancelling && <CancelPromise p={cancelling} onClose={() => setCancelling(null)} onDone={() => { setCancelling(null); onChanged(); }} />}
        </Card>
    );
}

function PromiseRow({ p, onKeep, onCancel }: { p: LeadPromise; onKeep: () => void; onCancel: () => void }) {
    const who = p.made_on === "team" ? `Promised by ${p.made_by ?? "the team"}` : `Promised ${MADE_ON[p.made_on] ?? p.made_on}${p.made_by ? ` by ${p.made_by}` : ""}`;
    const made = `${who} · ${formatWhen(p.made_at)}`;
    return (
        <li className="px-5 py-3 border-t border-line first:border-t-0">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium break-words">{p.what}</p>
                    <p className="text-xs text-stone-500 mt-0.5">{PROMISE_KIND[p.kind] ?? p.kind} · {made}</p>
                    {p.words && <p className="text-[13px] text-stone-600 mt-1 border-l-2 border-line pl-2 break-words">&ldquo;{p.words}&rdquo;</p>}
                    {p.status === "open" && (
                        <p className={`text-[13px] mt-1 ${p.late ? "text-signal" : "text-stone-600"}`}>
                            {p.late ? "Late: " : ""}{p.due_said ? "due" : "expected by"} {dueInline(p.due_at)}
                        </p>
                    )}
                    {p.status === "done" && p.evidence && (
                        <p className="text-[13px] text-stone-600 mt-1 break-words">
                            Kept: {p.evidence.text}{p.done_by ? ` · ${p.done_by}` : " · found in the records"}{p.done_at ? ` · ${formatWhen(p.done_at)}` : ""}
                        </p>
                    )}
                    {p.status === "cancelled" && <p className="text-[13px] text-stone-500 mt-1 break-words">Cancelled: {p.cancelled_why}{p.done_by ? ` · ${p.done_by}` : ""}</p>}
                </div>
                <div className="flex items-center gap-2">
                    {p.status === "open" ? <>
                        <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
                        <Button size="sm" onClick={onKeep}>It&apos;s done</Button>
                    </> : <Status tone={p.status === "done" ? "good" : "neutral"}>{p.status === "done" ? "Kept" : "Cancelled"}</Status>}
                </div>
            </div>
        </li>
    );
}

function AddPromise({ lead, onClose, onDone }: { lead: LeadDetail; onClose: () => void; onDone: () => void }) {
    const toast = useToast();
    const [kind, setKind] = useState<PromiseKind>("send");
    const [what, setWhat] = useState("");
    const [when, setWhen] = useState("");
    const [busy, setBusy] = useState(false);
    const save = async () => {
        setBusy(true);
        try {
            await apiJson(`/api/crm/leads/${lead.id}/promises`, { method: "POST", json: { kind, what: what.trim(), due_at: when ? new Date(when).toISOString() : null } });
            onDone();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    return (
        <Dialog open onClose={onClose} title="Add a promise" description="Something you or your team told them would be done, so it isn't forgotten."
                footer={<>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" disabled={busy || !what.trim()} onClick={save}>Add</Button>
                </>}>
            <div className="space-y-3">
                <label className="block">
                    <span className="text-xs text-stone-500">What was promised</span>
                    <Select className="mt-1" aria-label="Kind of promise" value={kind} onChange={(e) => setKind(e.target.value as PromiseKind)}>
                        {(Object.keys(PROMISE_KIND) as PromiseKind[]).map((k) => <option key={k} value={k}>{PROMISE_KIND[k]}</option>)}
                    </Select>
                </label>
                <label className="block">
                    <span className="text-xs text-stone-500">In a few words</span>
                    <Input className="mt-1" aria-label="What was promised" maxLength={200} placeholder="Send the 2BHK floor plan" value={what} onChange={(e) => setWhat(e.target.value)} />
                </label>
                <label className="block">
                    <span className="text-xs text-stone-500">By when (optional; else within a day)</span>
                    <Input className="mt-1" aria-label="By when" type="datetime-local" min={localInput(new Date())} value={when} onChange={(e) => setWhen(e.target.value)} />
                </label>
            </div>
        </Dialog>
    );
}

function KeepPromise({ p, how, onClose, onDone }: { p: LeadPromise; how: Record<string, string>; onClose: () => void; onDone: () => void }) {
    const toast = useToast();
    const [records, setRecords] = useState<PromiseEvidence[] | null>(null);
    const [picked, setPicked] = useState<string>("");  // "kind:id", or "own" for their own words
    const [way, setWay] = useState("call");
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState(false);
    useEffect(() => {
        apiJson<PromiseEvidence[]>(`/api/crm/promises/${p.id}/evidence`).then((r) => { setRecords(r); setPicked(r.length ? "" : "own"); })
            .catch((e) => { toast((e as Error).message); setRecords([]); setPicked("own"); });
    }, [p.id, toast]);
    const own = picked === "own";
    const save = async () => {
        setBusy(true);
        try {
            const [kind, ...rest] = picked.split(":");
            await apiJson(`/api/crm/promises/${p.id}/done`, { method: "POST", json: own ? { how: way, note: note.trim() } : { kind, id: rest.join(":") } });
            onDone();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    return (
        <Dialog open onClose={onClose} title="What kept this promise?" description={`${p.what}. Choose what did it, or write down what you did.`}
                footer={<>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" disabled={busy || !picked || (own && !note.trim())} onClick={save}>Save</Button>
                </>}>
            <div className="space-y-2 max-h-[55vh] overflow-y-auto pr-1">
                {records === null && [0, 1].map((i) => <Skeleton key={i} className="h-10" />)}
                {records?.length === 0 && <p className="text-[13px] text-stone-500">Nothing has been done for them in Nimmi since it was promised.</p>}
                {records?.map((r) => {
                    const key = `${r.kind}:${r.id}`;
                    return (
                        <label key={key} className={`flex items-start gap-2.5 rounded-md border px-3 py-2 text-[13px] cursor-pointer ${picked === key ? "border-plum bg-plum-tint" : "border-line"}`}>
                            <input type="radio" name="evidence" className="mt-0.5 accent-plum" checked={picked === key} onChange={() => setPicked(key)} />
                            <span className="min-w-0 flex-1">
                                <span className="block break-words">{r.text}</span>
                                {r.at && <span className="block text-xs text-stone-500">{formatWhen(r.at)}</span>}
                            </span>
                        </label>
                    );
                })}
                {records !== null && (
                    <label className={`flex items-start gap-2.5 rounded-md border px-3 py-2 text-[13px] cursor-pointer ${own ? "border-plum bg-plum-tint" : "border-line"}`}>
                        <input type="radio" name="evidence" className="mt-0.5 accent-plum" checked={own} onChange={() => setPicked("own")} />
                        <span className="min-w-0 flex-1">Done outside Nimmi: I&apos;ll write down what I did</span>
                    </label>
                )}
                {own && (
                    <div className="grid sm:grid-cols-[10rem_1fr] gap-2 pt-1">
                        <Select aria-label="How it was done" value={way} onChange={(e) => setWay(e.target.value)}>
                            {Object.entries(how).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                        </Select>
                        <Textarea aria-label="What you did" rows={2} maxLength={300} placeholder="Sent the floor plan from my phone at 4 pm" value={note} onChange={(e) => setNote(e.target.value)} />
                    </div>
                )}
            </div>
        </Dialog>
    );
}

function CancelPromise({ p, onClose, onDone }: { p: LeadPromise; onClose: () => void; onDone: () => void }) {
    const toast = useToast();
    const [why, setWhy] = useState("");
    const [busy, setBusy] = useState(false);
    const save = async () => {
        setBusy(true);
        try {
            await apiJson(`/api/crm/promises/${p.id}/cancel`, { method: "POST", json: { why: why.trim() } });
            onDone();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    return (
        <Dialog open onClose={onClose} title="Cancel this promise?" description={`${p.what}. It won't be done: say why, so your team knows.`}
                footer={<>
                    <Button variant="ghost" onClick={onClose}>Keep it open</Button>
                    <Button variant="danger" disabled={busy || !why.trim()} onClick={save}>Cancel the promise</Button>
                </>}>
            <Textarea aria-label="Why it won't be done" rows={2} maxLength={200} placeholder="They don't need it any more" value={why} onChange={(e) => setWhy(e.target.value)} />
        </Dialog>
    );
}
