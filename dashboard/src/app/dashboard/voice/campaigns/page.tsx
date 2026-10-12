"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus, Upload } from "lucide-react";
import {
    Button, Card, EmptyState, Input, SectionHeader, Segmented, Select, Sheet, Skeleton, Status, Textarea, cn, useToast,
} from "@/components/ui";
import { CampaignProgress, CAMPAIGN_STATUS } from "@/components/voice/CampaignBits";
import { parseCsv } from "@/lib/csv";
import { apiSave, useApi } from "@/lib/useApi";
import { formatDate } from "@/lib/voice/api";
import type { CampaignSummary, PhoneNumber, VoiceAgentSummary } from "@/lib/voice/types";

export default function CampaignsPage() {
    const campaigns = useApi<CampaignSummary[]>("/api/voice/campaigns");
    const [creating, setCreating] = useState(false);

    return (
        <>
            <SectionHeader
                title="Campaigns"
                description="Call a list of people who agreed to hear from you: follow-ups, reminders, renewals. Your assistant calls each person inside your calling hours and records what it finds out."
                action={<Button size="sm" variant="primary" onClick={() => setCreating(true)}><Plus size={14} /> New campaign</Button>}
            />
            <Card>
                {campaigns.loading ? (
                    <div className="p-5 space-y-3"><Skeleton className="h-14" /><Skeleton className="h-14" /></div>
                ) : !campaigns.data?.length ? (
                    <EmptyState
                        title="No campaigns yet"
                        body="Upload a list with a phone column (and any other details, like name or appointment date). Only call people who agreed to be contacted."
                        action={<Button variant="primary" onClick={() => setCreating(true)}>New campaign</Button>}
                    />
                ) : (
                    <ul>
                        {campaigns.data.map((c) => (
                            <li key={c.id} className="border-t border-line first:border-t-0">
                                <Link href={`/dashboard/voice/campaigns/${c.id}`}
                                      className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,16rem)_8rem] md:items-center px-5 py-4 hover:bg-stone-50 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-plum">
                                    <div className="min-w-0">
                                        <p className="text-sm font-medium truncate">{c.name}</p>
                                        <p className="text-[13px] text-stone-500 mt-0.5 truncate">{c.bot_name} · {formatDate(c.created_at)}</p>
                                    </div>
                                    <CampaignProgress counts={c.counts} />
                                    <div className="md:text-right"><Status tone={CAMPAIGN_STATUS[c.status].tone}>{CAMPAIGN_STATUS[c.status].label}</Status></div>
                                </Link>
                            </li>
                        ))}
                    </ul>
                )}
            </Card>
            <NewCampaign open={creating} onClose={() => setCreating(false)} />
        </>
    );
}

type Parsed = { contacts: { phone: string; name: string; variables: Record<string, string> }[]; columns: string[]; error: string };

const looksLikePhone = (s: string) => /^\+?[\d\s\-()]{8,}$/.test(s.trim());
const key = (header: string) => header.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");

/** Header row with a phone column (and optional name); every other column becomes a {{placeholder}}. */
function parseContacts(text: string): Parsed {
    const rows = parseCsv(text);
    if (!rows.length) return { contacts: [], columns: [], error: "" };
    if (looksLikePhone(rows[0][0] ?? "")) { // a plain list of numbers, no header
        return { contacts: rows.map((r) => ({ phone: r[0], name: r[1] ?? "", variables: {} })), columns: [], error: "" };
    }
    const header = rows[0].map(key);
    const phoneAt = header.findIndex((h) => /phone|mobile|number|contact|whatsapp/.test(h));
    if (phoneAt < 0) return { contacts: [], columns: [], error: "Add a column called phone (or mobile) to the first row." };
    const nameAt = header.findIndex((h, i) => i !== phoneAt && /name/.test(h));
    const extra = header.map((h, i) => ({ h, i })).filter(({ h, i }) => h && i !== phoneAt && i !== nameAt);
    const contacts = rows.slice(1).filter((r) => (r[phoneAt] ?? "").trim()).map((r) => ({
        phone: r[phoneAt],
        name: nameAt >= 0 ? r[nameAt] ?? "" : "",
        variables: Object.fromEntries(extra.map(({ h, i }) => [h, r[i] ?? ""]).filter(([, v]) => v)),
    }));
    return { contacts, columns: [...(nameAt >= 0 ? ["name"] : []), ...extra.map((e) => e.h)], error: "" };
}

function NewCampaign({ open, onClose }: { open: boolean; onClose: () => void }) {
    const toast = useToast();
    const router = useRouter();
    const agents = useApi<VoiceAgentSummary[]>(open ? "/api/voice/agents" : null);
    const numbers = useApi<PhoneNumber[]>(open ? "/api/voice/numbers" : null);
    const active = (numbers.data ?? []).filter((n) => n.status === "active");
    const ready = (agents.data ?? []).filter((a) => a.voice_id);

    const [name, setName] = useState("");
    const [botId, setBotId] = useState("");
    const [fromId, setFromId] = useState("");
    const [purpose, setPurpose] = useState("");
    const [list, setList] = useState("");
    const [fileName, setFileName] = useState("");
    const [windowStart, setWindowStart] = useState("10:00");
    const [windowEnd, setWindowEnd] = useState("19:00");
    const [attempts, setAttempts] = useState(2);
    const [parallel, setParallel] = useState(1);
    const [when, setWhen] = useState<"now" | "later">("now");
    const [startAt, setStartAt] = useState("");
    const [consent, setConsent] = useState(false);
    const [busy, setBusy] = useState(false);

    const parsed = useMemo(() => parseContacts(list), [list]);
    const bot = botId || ready[0]?.bot_id || "";
    const from = fromId || active[0]?.id || "";

    const loadFile = async (file?: File) => {
        if (!file) return;
        setFileName(file.name);
        setList(await file.text());
    };

    const submit = async () => {
        setBusy(true);
        const res = await apiSave("/api/voice/campaigns", "POST", {
            name, bot_id: bot, from_number_id: from, purpose, contacts: parsed.contacts,
            window_start: windowStart, window_end: windowEnd, max_attempts: attempts, concurrency: parallel,
            start_at: when === "later" && startAt ? new Date(startAt).toISOString() : null, consent,
        });
        setBusy(false);
        if (!res.ok) return toast(res.message);
        const c = res.data as CampaignSummary & { skipped: { invalid: number; duplicates: number; do_not_call: number } };
        const skipped = c.skipped.invalid + c.skipped.duplicates + c.skipped.do_not_call;
        toast(`${c.counts.total} people queued${skipped ? `, ${skipped} skipped` : ""}`);
        onClose();
        router.push(`/dashboard/voice/campaigns/${c.id}`);
    };

    const canSubmit = name.trim() && bot && from && purpose.trim().length >= 5 && parsed.contacts.length && consent && !busy
        && (when === "now" || startAt);
    const label = "text-[13px] font-medium";

    return (
        <Sheet open={open} onClose={onClose} title="New campaign" subtitle="Your assistant calls everyone on the list, one by one.">
            <div className="px-6 py-5 space-y-5">
                <div>
                    <label htmlFor="c_name" className={label}>Name</label>
                    <Input id="c_name" className="mt-1.5" placeholder="e.g. October site-visit follow-ups" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
                </div>

                <div className="grid sm:grid-cols-2 gap-3">
                    <div>
                        <label htmlFor="c_bot" className={label}>Assistant</label>
                        <Select id="c_bot" className="mt-1.5" value={bot} onChange={(e) => setBotId(e.target.value)} disabled={!ready.length}>
                            {!ready.length && <option value="">No assistant with a voice yet</option>}
                            {ready.map((a) => <option key={a.bot_id} value={a.bot_id}>{a.bot_name}</option>)}
                        </Select>
                    </div>
                    <div>
                        <label htmlFor="c_from" className={label}>Call from</label>
                        <Select id="c_from" className="mt-1.5" value={from} onChange={(e) => setFromId(e.target.value)} disabled={!active.length}>
                            {!active.length && <option value="">No active number</option>}
                            {active.map((n) => <option key={n.id} value={n.id}>{n.number}</option>)}
                        </Select>
                    </div>
                </div>

                <div>
                    <label htmlFor="c_purpose" className={label}>Why you&apos;re calling</label>
                    <Textarea id="c_purpose" className="mt-1.5" rows={3} maxLength={600} value={purpose} onChange={(e) => setPurpose(e.target.value)}
                              placeholder="e.g. Remind {{name}} about their appointment on {{date}} and confirm they can make it." />
                    <p className="text-xs text-stone-500 mt-1">
                        The assistant uses this to open the conversation. The agent&apos;s goal and fields to collect still apply.
                        {parsed.columns.length > 0 && <> Columns you can use: {parsed.columns.map((c) => <code key={c} className="mx-0.5 text-[11px] bg-stone-100 rounded px-1">{`{{${c}}}`}</code>)}</>}
                    </p>
                </div>

                <div>
                    <div className="flex items-center justify-between">
                        <span className={label}>People to call</span>
                        <label className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md border border-line-strong text-[13px] cursor-pointer hover:bg-stone-50 focus-within:outline-2 focus-within:outline-plum">
                            <Upload size={13} /> {fileName || "Upload CSV"}
                            <input type="file" accept=".csv,.txt,text/csv" className="sr-only" onChange={(e) => loadFile(e.target.files?.[0])} />
                        </label>
                    </div>
                    <Textarea aria-label="Paste your list" className="mt-1.5 font-mono text-xs" rows={5} value={list} onChange={(e) => { setList(e.target.value); setFileName(""); }}
                              placeholder={"phone,name,date\n9876543210,Ravi Kumar,14 Oct\n9812345678,Asha,15 Oct"} />
                    {parsed.error ? (
                        <p className="text-xs text-signal mt-1">{parsed.error}</p>
                    ) : parsed.contacts.length > 0 && (
                        <p className="text-xs text-stone-500 mt-1">
                            {parsed.contacts.length} {parsed.contacts.length === 1 ? "person" : "people"} found. Numbers on your do-not-call list, repeats and invalid numbers are skipped.
                        </p>
                    )}
                </div>

                <div>
                    <span className={label}>Calling hours</span>
                    <div className="flex items-center gap-2 mt-1.5">
                        <Input type="time" aria-label="From" className="w-32 tabular-nums" value={windowStart} onChange={(e) => setWindowStart(e.target.value)} />
                        <span className="text-xs text-stone-500">to</span>
                        <Input type="time" aria-label="Until" className="w-32 tabular-nums" value={windowEnd} onChange={(e) => setWindowEnd(e.target.value)} />
                        <span className="text-xs text-stone-500">India time</span>
                    </div>
                </div>

                <div className="grid sm:grid-cols-2 gap-3">
                    <div>
                        <label htmlFor="c_attempts" className={label}>If no answer</label>
                        <Select id="c_attempts" className="mt-1.5" value={attempts} onChange={(e) => setAttempts(Number(e.target.value))}>
                            <option value={1}>Don&apos;t retry</option>
                            <option value={2}>Retry once</option>
                            <option value={3}>Retry twice</option>
                        </Select>
                    </div>
                    <div>
                        <label htmlFor="c_parallel" className={label}>Calls at once</label>
                        <Select id="c_parallel" className="mt-1.5" value={parallel} onChange={(e) => setParallel(Number(e.target.value))}>
                            {[1, 2, 3, 5].map((n) => <option key={n} value={n}>{n}</option>)}
                        </Select>
                    </div>
                </div>
                <p className="text-xs text-stone-500 -mt-3">Retries happen an hour apart. A Twilio trial account can only make one call at a time.</p>

                <div>
                    <span className={label}>Start</span>
                    <div className="flex flex-wrap items-center gap-3 mt-1.5">
                        <Segmented label="Start" value={when} onChange={setWhen} options={[{ value: "now", label: "Now" }, { value: "later", label: "Later" }]} />
                        {when === "later" && <Input type="datetime-local" aria-label="Start at" className="max-w-56" value={startAt} onChange={(e) => setStartAt(e.target.value)} />}
                    </div>
                </div>

                <label className={cn("flex items-start gap-3 p-3 rounded-md border text-[13px] leading-relaxed cursor-pointer", consent ? "border-plum bg-plum-tint" : "border-line")}>
                    <input type="checkbox" className="mt-1 accent-[#550a64]" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
                    <span>
                        Everyone on this list asked to hear from us or is a customer who agreed to service calls.
                        <span className="block text-stone-500 mt-0.5">TRAI rules don&apos;t allow promotional calls to people who didn&apos;t agree. Anyone who asks to stop is added to your do-not-call list.</span>
                    </span>
                </label>

                <div className="flex justify-end gap-2 pt-2 border-t border-line">
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" onClick={submit} disabled={!canSubmit}>
                        {busy ? "Starting…" : when === "now" ? `Start calling ${parsed.contacts.length || ""}`.trim() : "Schedule campaign"}
                    </Button>
                </div>
            </div>
        </Sheet>
    );
}
