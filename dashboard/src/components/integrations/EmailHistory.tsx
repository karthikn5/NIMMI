"use client";

import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { Button, Card, Dialog, EmptyState, Input, Segmented, Select, Sheet, Skeleton, Status, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { AUTOMATIONS, type EmailHistory as History, type EmailRow, type EmailStatus } from "@/lib/integrations";
import { formatWhen, parseUtc } from "@/lib/voice/api";

const PAGE = 50;
type Filter = "" | EmailStatus;

const STATUS: Record<EmailStatus, { label: string; tone: "good" | "neutral" | "warn" | "bad" }> = {
    queued: { label: "Scheduled", tone: "warn" },
    sent: { label: "Sent", tone: "good" },
    failed: { label: "Failed", tone: "bad" },
    cancelled: { label: "Stopped", tone: "neutral" },
};

/** "In 3 hours", "Tomorrow, 10:30 am", or a past time. */
function when(row: EmailRow) {
    const iso = row.status === "sent" ? row.sent_at : row.send_at;
    if (!iso) return "";
    const d = parseUtc(iso);
    const ahead = d.getTime() - Date.now();
    if (row.status !== "queued" || ahead <= 60_000) return formatWhen(iso);
    const hours = ahead / 3_600_000;
    if (hours < 1) return `In ${Math.round(ahead / 60_000)} min`;
    if (hours < 24) return `In ${Math.round(hours)} ${Math.round(hours) === 1 ? "hour" : "hours"}`;
    return d.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

function kindLabel(row: EmailRow) {
    return row.step > 1 ? `${row.label}, follow-up ${row.step - 1}` : row.label;
}

export function EmailHistory() {
    const toast = useToast();
    const [status, setStatus] = useState<Filter>("");
    const [automation, setAutomation] = useState("");
    const [query, setQuery] = useState("");
    const [q, setQ] = useState("");
    const [data, setData] = useState<History | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loadingMore, setLoadingMore] = useState(false);
    const [openId, setOpenId] = useState<string | null>(null);

    useEffect(() => { const t = setTimeout(() => setQ(query), 300); return () => clearTimeout(t); }, [query]);

    const path = (offset: number) => `/api/integrations/email/history?${new URLSearchParams({
        status, automation, q, offset: String(offset), limit: String(PAGE),
    })}`;

    const load = async () => {
        setError(null);
        try {
            setData(await apiJson<History>(path(0)));
        } catch (e) {
            setError((e as Error).message);
        }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => { setData(null); load(); }, [status, automation, q]);

    const more = async () => {
        if (!data) return;
        setLoadingMore(true);
        try {
            const next = await apiJson<History>(path(data.items.length));
            setData({ ...next, items: [...data.items, ...next.items] });
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setLoadingMore(false);
        }
    };

    const all = data ? Object.values(data.counts).reduce((a, b) => a + b, 0) : 0;
    const count = (s: Filter) => (data ? (s ? data.counts[s] : all) : null);
    const label = (s: Filter, text: string) => (count(s) === null ? text : `${text} ${count(s)!.toLocaleString("en-IN")}`);

    return (
        <>
            <div className="flex flex-wrap items-center gap-3 mb-4">
                <div className="overflow-x-auto max-w-full [&_button]:whitespace-nowrap">
                    <Segmented label="Filter by status" value={status} onChange={setStatus} options={[
                        { value: "", label: label("", "All") }, { value: "queued", label: label("queued", "Scheduled") },
                        { value: "sent", label: label("sent", "Sent") }, { value: "failed", label: label("failed", "Failed") },
                        { value: "cancelled", label: label("cancelled", "Stopped") },
                    ]} />
                </div>
                <Select aria-label="Filter by email" className="w-48" value={automation} onChange={(e) => setAutomation(e.target.value)}>
                    <option value="">All emails</option>
                    {AUTOMATIONS.map((a) => <option key={a.key} value={a.key}>{a.title}</option>)}
                    <option value="broadcast">Bulk email</option>
                </Select>
                <div className="relative flex-1 min-w-48">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" aria-hidden />
                    <Input aria-label="Search by email or subject" placeholder="Search email address or subject" className="pl-8"
                           value={query} onChange={(e) => setQuery(e.target.value)} />
                </div>
            </div>

            <Card>
                {error ? <p className="p-5 text-sm text-signal">{error}</p> : !data ? (
                    <div className="p-5 space-y-3"><Skeleton className="h-10" /><Skeleton className="h-10" /><Skeleton className="h-10" /></div>
                ) : data.items.length === 0 ? (
                    <EmptyState title={status || automation || q ? "No emails match" : "No customer emails yet"}
                                body={status || automation || q ? "Try a different filter or search." : "Automatic follow-ups and bulk emails show here once they're scheduled or sent."} />
                ) : (
                    <>
                        <div className="hidden md:grid grid-cols-[minmax(0,1.1fr)_minmax(0,1.6fr)_minmax(0,1fr)_6.5rem_8.5rem] gap-x-4 px-5 py-2.5 border-b border-line text-xs text-stone-500">
                            <span>To</span><span>Subject</span><span>Email</span><span>Status</span><span className="text-right">When</span>
                        </div>
                        <ul>
                            {data.items.map((r) => (
                                <li key={r.id} className="border-t border-line first:border-t-0">
                                    <button type="button" onClick={() => setOpenId(r.id)}
                                            className="w-full text-left grid grid-cols-[minmax(0,1fr)_auto] md:grid-cols-[minmax(0,1.1fr)_minmax(0,1.6fr)_minmax(0,1fr)_6.5rem_8.5rem] gap-x-4 gap-y-0.5 px-5 py-3 text-[13px] hover:bg-stone-50 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-plum">
                                        <span className="truncate">{r.to}</span>
                                        <span className="md:hidden justify-self-end"><Status tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Status></span>
                                        <span className="truncate text-stone-700 col-span-2 md:col-span-1">{r.subject}</span>
                                        <span className="min-w-0 text-xs md:text-[13px] text-stone-500">
                                            <span className="block truncate">{r.label}{r.step > 1 && <span className="md:hidden">, follow-up {r.step - 1}</span>}</span>
                                            {r.step > 1 && <span className="hidden md:block text-xs text-stone-400">Follow-up {r.step - 1}</span>}
                                        </span>
                                        <span className="hidden md:block"><Status tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Status></span>
                                        <span className="text-xs text-stone-500 justify-self-end md:text-right tabular-nums">{when(r)}</span>
                                    </button>
                                </li>
                            ))}
                        </ul>
                        {data.items.length < data.total && (
                            <div className="px-5 py-3 border-t border-line text-center">
                                <Button size="sm" variant="ghost" onClick={more} disabled={loadingMore}>
                                    {loadingMore ? "Loading…" : `Show more (${(data.total - data.items.length).toLocaleString("en-IN")} left)`}
                                </Button>
                            </div>
                        )}
                    </>
                )}
            </Card>

            <EmailDetail id={openId} onClose={() => setOpenId(null)} onChanged={load} />
        </>
    );
}

type Detail = EmailRow & { body: string; unsubscribed: boolean };

function EmailDetail({ id, onClose, onChanged }: { id: string | null; onClose: () => void; onChanged: () => void }) {
    const toast = useToast();
    const [detail, setDetail] = useState<Detail | null>(null);
    const [busy, setBusy] = useState(false);
    const [stopping, setStopping] = useState(false);

    useEffect(() => {
        setDetail(null);
        if (!id) return;
        apiJson<Detail>(`/api/integrations/email/jobs/${id}`).then(setDetail).catch((e) => toast((e as Error).message));
    }, [id, toast]);

    const act = async (action: "resend" | "cancel") => {
        if (!detail) return;
        setBusy(true);
        try {
            const row = await apiJson<EmailRow>(`/api/integrations/email/jobs/${detail.id}/${action}`, { method: "POST" });
            setDetail({ ...detail, ...row });
            toast(action === "resend" ? "Sending again" : "Email stopped");
            onChanged();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    const stopPerson = async () => {
        if (!detail) return;
        setBusy(true);
        try {
            const r = await apiJson<{ cancelled: number }>("/api/integrations/email/stop", { method: "POST", json: { email: detail.to } });
            setDetail({ ...detail, unsubscribed: true, ...(detail.status === "queued" ? { status: "cancelled" as const, error: "Stopped by your team" } : {}) });
            toast(r.cancelled ? `Stopped. ${r.cancelled} scheduled ${r.cancelled === 1 ? "email" : "emails"} won't go out.` : "They won't get any more emails");
            setStopping(false);
            onChanged();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    return (
        <>
            <Sheet open={!!id} onClose={onClose} title={detail?.subject ?? "Email"} subtitle={detail ? `To ${detail.to}` : undefined}>
                {!detail ? <div className="p-6 space-y-3"><Skeleton className="h-5 w-48" /><Skeleton className="h-40" /></div> : (
                    <div className="p-6 space-y-5">
                        <dl className="grid grid-cols-[7rem_minmax(0,1fr)] gap-y-2 text-[13px]">
                            <dt className="text-stone-500">Status</dt>
                            <dd><Status tone={STATUS[detail.status].tone}>{STATUS[detail.status].label}</Status></dd>
                            <dt className="text-stone-500">Email</dt>
                            <dd>{kindLabel(detail)}</dd>
                            <dt className="text-stone-500">{detail.status === "sent" ? "Sent" : detail.status === "queued" ? "Goes out" : "Was due"}</dt>
                            <dd>{when(detail)}</dd>
                            {detail.error && <><dt className="text-stone-500">Why</dt><dd className="text-stone-700">{detail.error}</dd></>}
                            {detail.unsubscribed && <><dt className="text-stone-500">Person</dt><dd className="text-stone-700">Unsubscribed. They won&apos;t get more emails.</dd></>}
                        </dl>

                        <div className="rounded-md border border-line bg-paper p-3">
                            <div className="rounded-md bg-white border border-line px-4 py-4 text-[13px] leading-relaxed whitespace-pre-wrap break-words">
                                {detail.body}
                            </div>
                        </div>

                        <div className="flex flex-wrap gap-2">
                            {detail.status === "queued" && <Button onClick={() => act("cancel")} disabled={busy}>Don&apos;t send</Button>}
                            {(detail.status === "failed" || detail.status === "cancelled") && !detail.unsubscribed && (
                                <Button variant="primary" onClick={() => act("resend")} disabled={busy}>Send again</Button>
                            )}
                            {!detail.unsubscribed && <Button variant="ghost" onClick={() => setStopping(true)} disabled={busy}>Stop emailing this person</Button>}
                        </div>
                    </div>
                )}
            </Sheet>

            <Dialog open={stopping} onClose={() => setStopping(false)} title="Stop emailing this person?"
                    description={detail ? `${detail.to} won't get any more automatic or bulk emails from you. Anything scheduled for them is stopped.` : undefined}
                    footer={<>
                        <Button variant="ghost" onClick={() => setStopping(false)}>Cancel</Button>
                        <Button variant="danger" onClick={stopPerson} disabled={busy}>Stop emails</Button>
                    </>}>
                <p className="text-[13px] text-stone-600">This is the same as them clicking Unsubscribe.</p>
            </Dialog>
        </>
    );
}
