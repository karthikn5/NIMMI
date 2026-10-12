"use client";

import { useState } from "react";
import { Check, Lock, Plus, Upload } from "lucide-react";
import { BalanceCard, TopUpDialog, useBalance } from "@/components/Balance";
import { GetNumberDialog, NUMBER_KIND, countryName } from "@/components/voice/GetNumberDialog";
import {
    Button, Card, Dialog, EmptyState, Input, SaveBar, SectionHeader, Segmented, Select, SettingRow,
    Skeleton, Status, Switch, useToast,
} from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { apiSave, useApi, useDraft } from "@/lib/useApi";
import { formatDate, formatINR, formatWhen } from "@/lib/voice/api";
import type { CallbackJob, CallbackSettings, PhoneNumber, VoiceAgentSummary } from "@/lib/voice/types";

const STATUS: Record<PhoneNumber["status"], { label: string; tone: "good" | "warn" | "neutral" }> = {
    active: { label: "Active", tone: "good" },
    pending_kyc: { label: "Waiting for documents", tone: "warn" },
    provisioning: { label: "Setting up", tone: "neutral" },
    suspended: { label: "Paused, balance too low", tone: "warn" },
};

export default function NumbersPage() {
    const toast = useToast();
    const numbers = useApi<PhoneNumber[]>("/api/voice/numbers");
    const agents = useApi<VoiceAgentSummary[]>("/api/voice/agents");
    const [requestOpen, setRequestOpen] = useState(false);
    const [docsFor, setDocsFor] = useState<PhoneNumber | null>(null);
    const [releasing, setReleasing] = useState<PhoneNumber | null>(null);
    const [topUp, setTopUp] = useState(false);
    const wallet = useBalance();

    const replace = (n: PhoneNumber) => numbers.setData((numbers.data ?? []).map((x) => (x.id === n.id ? n : x)));

    const route = async (n: PhoneNumber, botId: string) => {
        const res = await apiSave(`/api/voice/numbers/${n.id}`, "PATCH", { bot_id: botId || null });
        if (!res.ok) return toast(res.message);
        replace(res.data as PhoneNumber);
        const name = agents.data?.find((a) => a.bot_id === botId)?.bot_name;
        toast(name ? `${n.number} now goes to ${name}` : `${n.number} won't be answered`);
    };

    const active = (numbers.data ?? []).filter((n) => n.status === "active");
    const selfServe = (numbers.data ?? []).some((n) => n.next_charge_at); // bought here, paid from the balance

    return (
        <>
            <section>
                <SectionHeader
                    title="Phone numbers"
                    description="Customers call these numbers to reach an assistant. Each number goes to one assistant."
                    action={<Button size="sm" onClick={() => setRequestOpen(true)}><Plus size={14} /> Get a number</Button>}
                />
                <Card>
                    {numbers.loading ? (
                        <div className="p-5 space-y-3"><Skeleton className="h-12" /><Skeleton className="h-12" /></div>
                    ) : !numbers.data?.length ? (
                        <EmptyState
                            title="No phone numbers yet"
                            body="You can still test every assistant in your browser. Get a number when you're ready to take real calls."
                            action={<Button variant="primary" onClick={() => setRequestOpen(true)}>Get a number</Button>}
                        />
                    ) : (
                        <ul>
                            {numbers.data.map((n) => (
                                <li key={n.id} className="grid gap-3 md:grid-cols-[minmax(0,1fr)_220px_150px] md:items-center px-5 py-4 border-t border-line first:border-t-0">
                                    <div>
                                        <p className="text-sm font-medium tabular-nums">{n.number}</p>
                                        <p className="text-[13px] text-stone-500 mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                                            <span>
                                                {n.country ? countryName(n.country) : n.city} · {NUMBER_KIND[n.kind] ?? n.kind} · {formatINR(n.monthly_fee)}/month
                                                {n.status === "active" && n.next_charge_at && ` · Renews ${formatDate(n.next_charge_at)}`}
                                            </span>
                                            <Status tone={STATUS[n.status].tone}>{STATUS[n.status].label}</Status>
                                        </p>
                                    </div>
                                    <Select
                                        aria-label={`Assistant for ${n.number}`}
                                        value={n.bot_id ?? ""}
                                        disabled={n.status !== "active" && n.status !== "suspended"}
                                        onChange={(e) => route(n, e.target.value)}
                                    >
                                        <option value="">Not answered</option>
                                        {(agents.data ?? []).map((a) => <option key={a.bot_id} value={a.bot_id}>{a.bot_name}</option>)}
                                    </Select>
                                    <div className="md:text-right">
                                        {n.status === "pending_kyc" && (
                                            <Button size="sm" variant="primary" onClick={() => setDocsFor(n)}><Upload size={13} /> Upload documents</Button>
                                        )}
                                        {n.status === "provisioning" && <span className="text-xs text-stone-500">Usually 2 to 5 working days</span>}
                                        {n.status === "suspended" && (
                                            <Button size="sm" variant="primary" onClick={() => setTopUp(true)}>Add money</Button>
                                        )}
                                        {n.status === "active" && n.next_charge_at && (
                                            <Button size="sm" variant="ghost" onClick={() => setReleasing(n)}>Release</Button>
                                        )}
                                    </div>
                                </li>
                            ))}
                        </ul>
                    )}
                </Card>
                {(selfServe || (wallet.data?.balance ?? 0) > 0) && (
                    <div className="mt-4">
                        <h3 className="text-sm font-medium mb-2">Nimmi balance</h3>
                        <BalanceCard info={wallet} onPaid={numbers.reload} />
                    </div>
                )}
            </section>

            <CallbackSection activeNumbers={active} />

            <GetNumberDialog
                open={requestOpen}
                agents={agents.data ?? []}
                onClose={() => setRequestOpen(false)}
                onCreated={(n) => {
                    numbers.setData([...(numbers.data ?? []), n]);
                    wallet.reload();
                    if (n.status === "pending_kyc") setDocsFor(n);
                }}
            />
            <ReleaseDialog
                number={releasing}
                onClose={() => setReleasing(null)}
                onReleased={(n) => { numbers.setData((numbers.data ?? []).filter((x) => x.id !== n.id)); wallet.reload(); }}
            />
            <TopUpDialog
                open={topUp}
                onClose={() => setTopUp(false)}
                amounts={wallet.data?.topups ?? [500, 1000, 2000, 5000]}
                needed={Math.max(0, (wallet.data?.monthly_commitment ?? 0) - (wallet.data?.balance ?? 0))}
                onPaid={() => { wallet.reload(); numbers.reload(); }}
            />
            <DocumentsDialog number={docsFor} onClose={() => setDocsFor(null)} onUpdated={(n) => { replace(n); setDocsFor(n.status === "pending_kyc" ? n : null); }} />
        </>
    );
}

function CallbackSection({ activeNumbers }: { activeNumbers: PhoneNumber[] }) {
    const toast = useToast();
    const settings = useApi<CallbackSettings>("/api/voice/callbacks");
    const jobs = useApi<CallbackJob[]>("/api/voice/callbacks/jobs");
    const { draft, setDraft, dirty, saving, save, discard } = useDraft(settings, "/api/voice/callbacks");
    const noNumber = activeNumbers.length === 0;

    if (!draft) return <Skeleton className="h-64 mt-10" />;
    const set = <K extends keyof CallbackSettings>(k: K, v: CallbackSettings[K]) => setDraft({ ...draft, [k]: v });

    return (
        <section id="callbacks" className="mt-10 scroll-mt-6">
            <SectionHeader
                title="Call back new leads"
                description="When someone leaves their number in chat or on a form and asks to be called, your assistant rings them. Calling quickly, while they're still interested, matters most."
            />
            <Card className="px-5 py-1">
                <SettingRow label="Callbacks" hint={noNumber ? "Get a phone number first. Callbacks need a number to call from." : undefined}>
                    <label className="flex items-center gap-3 text-sm">
                        <Switch checked={draft.enabled} onChange={(v) => set("enabled", v)} label="Call back new leads" disabled={noNumber} />
                        <span className="text-stone-600">{draft.enabled ? "On" : "Off"}</span>
                    </label>
                </SettingRow>

                <SettingRow label="Who gets a call">
                    <p className="flex items-start gap-2 text-sm">
                        <Lock size={13} className="mt-1 text-stone-400 shrink-0" aria-hidden />
                        <span>
                            Only people who asked for one.
                            <span className="block text-[13px] text-stone-500 mt-1">
                                Your chat widget asks for permission before it saves a number. Calling people who didn&apos;t ask is against TRAI rules, so it isn&apos;t possible here.
                            </span>
                        </span>
                    </p>
                </SettingRow>

                <SettingRow label="Call them">
                    <Segmented
                        label="Call delay"
                        value={draft.delay}
                        onChange={(v) => set("delay", v)}
                        options={[
                            { value: "immediate", label: "Right away" },
                            { value: "1m", label: "After 1 min" },
                            { value: "5m", label: "5 min" },
                            { value: "15m", label: "15 min" },
                        ]}
                    />
                </SettingRow>

                <SettingRow label="Calling hours" hint="Requests outside these hours are called at the start of the next window.">
                    <div className="flex items-center gap-2">
                        <Input type="time" aria-label="From" className="w-32 tabular-nums" value={draft.window_start} onChange={(e) => set("window_start", e.target.value)} />
                        <span className="text-[13px] text-stone-500">to</span>
                        <Input type="time" aria-label="Until" className="w-32 tabular-nums" value={draft.window_end} onChange={(e) => set("window_end", e.target.value)} />
                    </div>
                </SettingRow>

                <SettingRow label="If they don't pick up" htmlFor="attempts">
                    <Select id="attempts" className="max-w-56" value={draft.max_attempts} onChange={(e) => set("max_attempts", Number(e.target.value))}>
                        <option value={1}>Don&apos;t try again</option>
                        <option value={2}>Try once more after 1 hour</option>
                        <option value={3}>Try twice more, 1 hour apart</option>
                    </Select>
                </SettingRow>

                <SettingRow label="Call from" htmlFor="from_number" hint="People see this number. Use one they'll recognise from your website.">
                    <Select id="from_number" className="max-w-64" value={draft.from_number_id ?? ""} disabled={noNumber} onChange={(e) => set("from_number_id", e.target.value || null)}>
                        {noNumber && <option value="">No active number</option>}
                        {!noNumber && !activeNumbers.some((n) => n.id === draft.from_number_id) && <option value="">Choose a number</option>}
                        {activeNumbers.map((n) => <option key={n.id} value={n.id}>{n.number}</option>)}
                    </Select>
                </SettingRow>
            </Card>

            <SaveBar visible={dirty} saving={saving} onDiscard={discard} onSave={async () => toast(await save())} />

            {(jobs.data?.length ?? 0) > 0 && (
                <div className="mt-6">
                    <h3 className="text-sm font-medium mb-3">Recent callback requests</h3>
                    <Card>
                        <ul>
                            {jobs.data!.slice(0, 10).map((j) => (
                                <li key={j.id} className="grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,1fr)_9rem_minmax(0,1.2fr)] gap-x-4 gap-y-1 px-5 py-3 border-t border-line first:border-t-0 text-[13px]">
                                    <div className="min-w-0">
                                        <p className="tabular-nums">{j.number}</p>
                                        {j.name && <p className="text-xs text-stone-500 truncate">{j.name}</p>}
                                    </div>
                                    <Status tone={JOB_TONE[j.status]}>{JOB_LABEL[j.status]}</Status>
                                    <p className="col-span-2 sm:col-span-1 text-xs text-stone-500">
                                        {j.status === "queued" && j.next_attempt_at ? `Next try ${formatWhen(j.next_attempt_at).toLowerCase()}` : ""}
                                        {j.status !== "queued" && j.last_error ? j.last_error : ""}
                                        {j.attempts > 0 ? ` · ${j.attempts} ${j.attempts === 1 ? "attempt" : "attempts"}` : ""}
                                    </p>
                                </li>
                            ))}
                        </ul>
                    </Card>
                </div>
            )}
        </section>
    );
}

const JOB_LABEL: Record<CallbackJob["status"], string> = {
    queued: "Waiting", calling: "Calling", done: "Called", failed: "Not reached", cancelled: "Cancelled",
};
const JOB_TONE: Record<CallbackJob["status"], "good" | "warn" | "neutral" | "bad"> = {
    queued: "neutral", calling: "neutral", done: "good", failed: "bad", cancelled: "warn",
};

function DocumentsDialog({ number, onClose, onUpdated }: { number: PhoneNumber | null; onClose: () => void; onUpdated: (n: PhoneNumber) => void }) {
    const toast = useToast();
    const [busy, setBusy] = useState<string | null>(null);

    const upload = async (kind: "coi" | "gst", file: File | undefined) => {
        if (!file || !number) return;
        setBusy(kind);
        const form = new FormData();
        form.append("kind", kind);
        form.append("file", file);
        try {
            const res = await apiFetch(`/api/voice/numbers/${number.id}/documents`, { method: "POST", body: form });
            const body = await res.json();
            if (!res.ok) throw new Error(body.detail || "Upload failed");
            onUpdated(body as PhoneNumber);
            toast(body.status === "provisioning" ? "Both documents received. We'll set up your number." : "Uploaded");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(null);
        }
    };

    const docs: { kind: "coi" | "gst"; label: string }[] = [
        { kind: "coi", label: "Certificate of Incorporation" },
        { kind: "gst", label: "GST certificate" },
    ];

    return (
        <Dialog
            open={!!number}
            onClose={onClose}
            title="Upload business documents"
            description="Telecom rules require both before a number can be issued. PDF, PNG or JPG, up to 10 MB. Only our team sees them."
            footer={<Button onClick={onClose}>Done</Button>}
        >
            <ul className="space-y-2">
                {docs.map((d) => {
                    const done = number?.documents?.includes(d.kind);
                    return (
                        <li key={d.kind} className="flex items-center gap-3 px-4 py-3 rounded-md border border-line">
                            <span className="flex-1 text-sm">{d.label}</span>
                            {done && <span className="inline-flex items-center gap-1 text-xs text-emerald-700"><Check size={13} /> Uploaded</span>}
                            <label className="inline-flex items-center h-8 px-3 rounded-md border border-line-strong text-[13px] cursor-pointer hover:bg-stone-50 focus-within:outline-2 focus-within:outline-plum">
                                {busy === d.kind ? "Uploading…" : done ? "Replace" : "Choose file"}
                                <input type="file" accept=".pdf,.png,.jpg,.jpeg" className="sr-only" disabled={!!busy}
                                       onChange={(e) => upload(d.kind, e.target.files?.[0])} />
                            </label>
                        </li>
                    );
                })}
            </ul>
        </Dialog>
    );
}

function ReleaseDialog({ number, onClose, onReleased }: { number: PhoneNumber | null; onClose: () => void; onReleased: (n: PhoneNumber) => void }) {
    const toast = useToast();
    const [busy, setBusy] = useState(false);

    const release = async () => {
        if (!number) return;
        setBusy(true);
        const res = await apiSave(`/api/voice/numbers/${number.id}`, "DELETE");
        setBusy(false);
        if (!res.ok) return toast(res.message);
        toast(`${number.number} released`);
        onReleased(number);
        onClose();
    };

    return (
        <Dialog
            open={!!number}
            onClose={onClose}
            title={`Release ${number?.number ?? ""}?`}
            description="It stops taking calls right away and goes back to the carrier. You can't get the same number back, and the rest of this month isn't refunded."
            footer={<>
                <Button variant="ghost" onClick={onClose}>Keep number</Button>
                <Button variant="danger" onClick={release} disabled={busy}>{busy ? "Releasing…" : "Release number"}</Button>
            </>}
        >
            <p className="text-[13px] text-stone-600">Callbacks that use this number will need another one to call from.</p>
        </Dialog>
    );
}
