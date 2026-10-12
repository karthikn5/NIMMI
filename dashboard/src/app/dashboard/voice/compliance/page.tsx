"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Download, Lock, Plus, Search } from "lucide-react";
import {
    Button, Card, Dialog, EmptyState, Input, PhraseInput, SaveBar, SectionHeader, Segmented, SettingRow,
    Skeleton, Switch, useToast,
} from "@/components/ui";
import { apiSave, useApi, useDraft } from "@/lib/useApi";
import { formatDate } from "@/lib/voice/api";
import type { ComplianceSettings, DncEntry } from "@/lib/voice/types";

const REASON: Record<DncEntry["reason"], string> = {
    caller_request: "Asked during a call",
    manual: "Added by you",
    imported: "Imported",
};

export default function CompliancePage() {
    const toast = useToast();
    const settings = useApi<ComplianceSettings>("/api/voice/compliance");
    const { draft, setDraft, dirty, saving, save, discard } = useDraft(settings, "/api/voice/compliance");

    if (settings.loading || !draft) return <Skeleton className="h-96" />;
    const set = <K extends keyof ComplianceSettings>(k: K, v: ComplianceSettings[K]) => setDraft({ ...draft, [k]: v });

    return (
        <>
            <section>
                <SectionHeader title="Calls and recordings" description="How callers are told about the assistant, and how long you keep what they said." />
                <Card className="px-5 py-1">
                    <SettingRow label="Automated call notice">
                        <p className="flex items-start gap-2 text-sm">
                            <Lock size={13} className="mt-1 text-stone-400 shrink-0" aria-hidden />
                            <span>
                                Always on.
                                <span className="block text-[13px] text-stone-500 mt-1">
                                    Every call opens by saying the caller is talking to an automated assistant and that the call may be recorded.
                                    Edit the wording per assistant under <Link href="/dashboard/voice/agents" className="text-plum underline underline-offset-2">Agents</Link>.
                                </span>
                            </span>
                        </p>
                    </SettingRow>
                    <SettingRow label="Record calls" hint="Useful for checking quality and settling disputes.">
                        <Switch checked={draft.record_calls} onChange={(v) => set("record_calls", v)} label="Record calls" />
                    </SettingRow>
                    <SettingRow label="Keep recordings and transcripts" hint="Deleted automatically after this. Lead details you've collected stay until you delete them.">
                        <Segmented
                            label="Retention period"
                            value={String(draft.retention_days)}
                            onChange={(v) => set("retention_days", Number(v) as ComplianceSettings["retention_days"])}
                            options={[{ value: "30", label: "30 days" }, { value: "90", label: "90 days" }, { value: "180", label: "180 days" }]}
                        />
                    </SettingRow>
                    <SettingRow
                        label="When a caller says"
                        hint="The assistant confirms, ends the call politely and adds the number to your do-not-call list. It also catches other ways of saying the same thing."
                    >
                        <PhraseInput label="Opt-out phrases" value={draft.opt_out_phrases} onChange={(v) => set("opt_out_phrases", v)} placeholder="e.g. don't call me" />
                    </SettingRow>
                </Card>
            </section>

            <DncSection />
            <EraseSection />

            <SaveBar visible={dirty} saving={saving} onDiscard={discard} onSave={async () => toast(await save())} />
        </>
    );
}

function DncSection() {
    const toast = useToast();
    const list = useApi<DncEntry[]>("/api/voice/dnc");
    const [query, setQuery] = useState("");
    const [adding, setAdding] = useState(false);
    const [number, setNumber] = useState("");

    const rows = useMemo(() => {
        const q = query.replace(/\s/g, "");
        return (list.data ?? []).filter((d) => !q || d.number.replace(/\s/g, "").includes(q));
    }, [list.data, query]);

    const add = async () => {
        const clean = number.trim();
        if (clean.replace(/\D/g, "").length < 10) return toast("Enter a full 10-digit number.");
        const res = await apiSave("/api/voice/dnc", "POST", { number: clean });
        if (res.ok) {
            const entry = res.data as DncEntry;
            list.setData([entry, ...(list.data ?? []).filter((d) => d.id !== entry.id)]);
        }
        toast(res.ok ? "Added to the do-not-call list" : res.message);
        setNumber("");
        setAdding(false);
    };

    const remove = async (d: DncEntry) => {
        const res = await apiSave(`/api/voice/dnc/${d.id}`, "DELETE");
        if (res.ok) list.setData((list.data ?? []).filter((x) => x.id !== d.id));
        toast(res.ok ? `${d.number} can be called again` : res.message);
    };

    const exportCsv = () => {
        const csv = ["number,reason,added_at", ...(list.data ?? []).map((d) => `"${d.number}",${d.reason},${d.added_at}`)].join("\n");
        const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
        Object.assign(document.createElement("a"), { href: url, download: "do-not-call.csv" }).click();
        URL.revokeObjectURL(url);
    };

    return (
        <section className="mt-10">
            <SectionHeader
                title="Do-not-call list"
                description="Your assistants never call these numbers. Callers who ask to stop are added automatically."
                action={
                    <div className="flex gap-2">
                        <Button size="sm" variant="ghost" onClick={exportCsv} disabled={!list.data?.length}><Download size={14} /> Export</Button>
                        <Button size="sm" onClick={() => setAdding(true)}><Plus size={14} /> Add number</Button>
                    </div>
                }
            />
            <Card>
                {list.loading ? (
                    <div className="p-5 space-y-3"><Skeleton className="h-10" /><Skeleton className="h-10" /></div>
                ) : !list.data?.length ? (
                    <EmptyState title="The list is empty" body="Numbers appear here when a caller asks not to be called, or when you add one." />
                ) : (
                    <>
                        <div className="p-3 border-b border-line">
                            <div className="relative sm:max-w-72">
                                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" aria-hidden />
                                <Input aria-label="Search the do-not-call list" placeholder="Search number" className="pl-8" value={query} onChange={(e) => setQuery(e.target.value)} />
                            </div>
                        </div>
                        <ul>
                            {rows.map((d) => (
                                <li key={d.id} className="flex items-center gap-4 px-5 py-3 border-t border-line first:border-t-0">
                                    <div className="flex-1 min-w-0 sm:grid sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_120px] sm:items-center sm:gap-4">
                                        <p className="text-sm tabular-nums">{d.number}</p>
                                        <p className="text-[13px] text-stone-500">{REASON[d.reason]}</p>
                                        <p className="text-[13px] text-stone-500">{formatDate(d.added_at)}</p>
                                    </div>
                                    <Button size="sm" variant="ghost" onClick={() => remove(d)}>Remove</Button>
                                </li>
                            ))}
                            {rows.length === 0 && <li className="px-5 py-6 text-[13px] text-stone-500">No numbers match “{query}”.</li>}
                        </ul>
                    </>
                )}
            </Card>

            <Dialog
                open={adding}
                onClose={() => setAdding(false)}
                title="Add to do-not-call list"
                footer={<>
                    <Button variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>
                    <Button variant="primary" onClick={add}>Add number</Button>
                </>}
            >
                <label htmlFor="dnc-number" className="text-sm font-medium">Phone number</label>
                <Input
                    id="dnc-number"
                    type="tel"
                    inputMode="tel"
                    autoFocus
                    placeholder="+91 98765 43210"
                    className="mt-1.5 tabular-nums"
                    value={number}
                    onChange={(e) => setNumber(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && add()}
                />
            </Dialog>
        </section>
    );
}

function EraseSection() {
    const toast = useToast();
    const [number, setNumber] = useState("");
    const [confirming, setConfirming] = useState(false);
    const [busy, setBusy] = useState(false);

    const erase = async () => {
        setBusy(true);
        const res = await apiSave("/api/voice/erase", "POST", { number: number.trim() });
        setBusy(false);
        setConfirming(false);
        toast(res.ok ? "Erased. Their calls, recordings and details are gone." : res.message);
        if (res.ok) setNumber("");
    };

    return (
        <section className="mt-10">
            <SectionHeader title="Erase a caller's data" description="When someone asks you to delete their information, erase it here. It removes their calls, recordings, transcripts and collected details." />
            <Card className="p-5">
                <form className="flex flex-col sm:flex-row gap-3" onSubmit={(e) => { e.preventDefault(); if (number.replace(/\D/g, "").length >= 10) setConfirming(true); else toast("Enter a full 10-digit number."); }}>
                    <Input type="tel" inputMode="tel" aria-label="Caller's phone number" placeholder="+91 98765 43210" className="sm:max-w-64 tabular-nums" value={number} onChange={(e) => setNumber(e.target.value)} />
                    <Button type="submit" variant="danger">Erase data</Button>
                </form>
            </Card>

            <Dialog
                open={confirming}
                onClose={() => setConfirming(false)}
                title={`Erase all data for ${number}?`}
                description="This can't be undone. The number is also added to your do-not-call list."
                footer={<>
                    <Button variant="ghost" onClick={() => setConfirming(false)}>Cancel</Button>
                    <Button variant="danger" onClick={erase} disabled={busy}>{busy ? "Erasing…" : "Erase permanently"}</Button>
                </>}
            >
                <p className="text-[13px] text-stone-600">Calls, recordings, transcripts and lead details linked to this number will be deleted across all your assistants.</p>
            </Dialog>
        </section>
    );
}
