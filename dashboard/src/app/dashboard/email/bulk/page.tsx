"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus, Upload } from "lucide-react";
import { Button, Card, EmptyState, Input, Select, Skeleton, Status, Switch, useToast } from "@/components/ui";
import { BulkEditor, OPEN_STATUSES, atText, statusOf } from "@/components/email/BulkEditor";
import { ImportContacts } from "@/components/email/ImportContacts";
import { apiJson } from "@/lib/api";
import type { BulkEmail, BulkPage, Senders } from "@/lib/email";
import { PlanNeeded, useLimits } from "@/lib/plan";
import { useApi } from "@/lib/useApi";

function line(b: BulkEmail) {
    const c = b.counts;
    const when = b.status === "scheduled" && b.send_at ? `Goes ${atText(b.send_at)}` : b.started_at ? atText(b.started_at) : b.created_at ? `Written ${atText(b.created_at)}` : "";
    const done = c && b.status !== "draft" ? [`${b.recipients} ${b.recipients === 1 ? "person" : "people"}`, `${c.delivered} delivered`, c.clicked ? `${c.clicked} clicked` : "",
        c.replied ? `${c.replied} replied` : "", c.complained ? `${c.complained} spam ${c.complained === 1 ? "report" : "reports"}` : ""] : [];
    return [when, ...done].filter(Boolean).join(" · ");
}

function AskInChat({ page, botId, onChanged }: { page: BulkPage; botId: string; onChanged: () => void }) {
    const toast = useToast();
    const [words, setWords] = useState(page.ask_in_chat.words);
    const [busy, setBusy] = useState(false);
    const set = async (values: Record<string, unknown>) => {
        setBusy(true);
        try {
            await apiJson(`/api/email/setup/${botId}`, { method: "PUT", json: { settings: { consent: values } } });
            onChanged();
            toast("Saved");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    return (
        <div className="border-t border-line px-5 py-4">
            <div className="flex flex-wrap items-center gap-3">
                <div className="flex-1 min-w-48">
                    <p className="text-sm">Ask in the chat</p>
                    <p className="text-[13px] text-stone-500 mt-0.5">A box under the chat&apos;s email question, never ticked for them. Their tick, and these words, are kept as the record.</p>
                </div>
                <Switch checked={page.ask_in_chat.ask} disabled={busy} onChange={(v) => set({ ask: v })} label="Ask in the chat" />
            </div>
            {page.ask_in_chat.ask && (
                <div className="flex flex-wrap gap-2 mt-3">
                    <Input aria-label="The words next to the box" className="flex-1 min-w-48" maxLength={200} value={words} onChange={(e) => setWords(e.target.value)} />
                    <Button size="sm" disabled={busy || words.trim().length < 5 || words === page.ask_in_chat.words} onClick={() => set({ words: words.trim() })}>Save the words</Button>
                </div>
            )}
        </div>
    );
}

function BulkPageInner() {
    const toast = useToast();
    const router = useRouter();
    const params = useSearchParams();
    const limits = useLimits();
    const senders = useApi<Senders>("/api/email/senders");
    const [botId, setBotId] = useState("");
    const page = useApi<BulkPage>(botId ? `/api/email/bulk/${botId}` : null);
    const [importing, setImporting] = useState(false);
    const [busy, setBusy] = useState(false);
    const assistants = senders.data?.assistants ?? [];
    const openId = params.get("send");
    const { reload } = page;
    useEffect(() => { if (!botId && assistants[0]) setBotId(assistants[0].bot_id); }, [botId, assistants]);
    const going = !!page.data?.broadcasts.some((b) => OPEN_STATUSES.includes(b.status));
    useEffect(() => {
        if (!going || openId) return;
        const t = setInterval(() => { void reload(); }, 10_000);
        return () => clearInterval(t);
    }, [going, openId, reload]);

    const show = (id: string | null) => router.replace(id ? `/dashboard/email/bulk?send=${id}` : "/dashboard/email/bulk", { scroll: false });
    const create = async () => {
        setBusy(true);
        try {
            const made = await apiJson<BulkEmail>("/api/email/broadcasts", { method: "POST", json: { bot_id: botId, subject: "", body: "" } });
            show(made.id);
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    if (senders.error) return <p className="text-sm text-signal">{senders.error}</p>;
    if (!senders.data) return <Skeleton className="h-64" />;
    if (assistants.length === 0) return <Card className="p-5 text-[13px] text-stone-600">Make an assistant first: bulk email goes out in its name.</Card>;
    if (page.error) return <p className="text-sm text-signal">{page.error}</p>;
    const d = page.data;
    if (!d) return <Skeleton className="h-64" />;
    if (openId) return <BulkEditor key={openId} id={openId} page={d} botId={botId} onBack={() => show(null)} onChanged={() => { void reload(); }} />;
    const plan = limits?.assistant_plans?.[botId];
    const growth = plan ? plan.email_alerts : limits?.includes?.email_alerts ?? true;
    const mine = d.broadcasts.filter((b) => b.bot_id), earlier = d.broadcasts.filter((b) => !b.bot_id);
    const business = assistants.find((a) => a.bot_id === botId)?.bot_name ?? "your business";
    return (
        <div className="space-y-5">
            {!growth && <PlanNeeded feature="email_alerts" botId={botId}>Get your bulk emails ready here. They go out on Growth or Pro.</PlanNeeded>}
            <Card>
                <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4 pb-4">
                    <div className="min-w-0">
                        <h3 className="text-sm font-medium">Who can get offers and news</h3>
                        <p className="text-[13px] text-stone-500 mt-0.5">
                            <span className="text-ink tabular-nums">{d.agreed}</span> of the {d.with_email} people with an email agreed. Bulk email goes only to them; emails about their own enquiry aren&apos;t affected.
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        {assistants.length > 1 && (
                            <Select aria-label="Assistant" className="w-56" value={botId} onChange={(e) => setBotId(e.target.value)}>
                                {assistants.map((a) => <option key={a.bot_id} value={a.bot_id}>{a.bot_name}</option>)}
                            </Select>
                        )}
                        <Button size="sm" onClick={() => setImporting(true)}><Upload size={13} aria-hidden /> Import a list</Button>
                    </div>
                </div>
                <AskInChat key={botId} page={d} botId={botId} onChanged={() => { void reload(); }} />
                <p className="border-t border-line px-5 py-3 text-[13px] text-stone-500">
                    You can also note someone&apos;s yes on Leads &gt; Board, and website forms with a newsletter box send it with the lead.
                </p>
            </Card>
            <Card>
                <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4 pb-3">
                    <div className="min-w-0">
                        <h3 className="text-sm font-medium">Bulk emails</h3>
                        <p className="text-[13px] text-stone-500 mt-0.5">
                            From {d.sender.name} &lt;{d.sender.address}&gt;.{" "}
                            {d.room_today === null ? "No daily limit." : `${d.room_today} more can go today.`}
                            {!d.sender.domain && " Your own domain (Email > Settings) has no daily limit once it has warmed up."}
                        </p>
                    </div>
                    <Button variant="primary" disabled={busy} onClick={create}><Plus size={14} aria-hidden /> New bulk email</Button>
                </div>
                {mine.length === 0 ? (
                    <div className="border-t border-line"><EmptyState title="No bulk emails yet" body="Write one to the people who agreed to hear from you: an offer, news, an invitation." /></div>
                ) : (
                    <ul>
                        {mine.map((b) => {
                            const s = statusOf(b);
                            return (
                                <li key={b.id} className="border-t border-line">
                                    <button type="button" onClick={() => show(b.id)} className="w-full flex flex-wrap items-center gap-3 px-5 py-3.5 text-left hover:bg-paper/70 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-plum">
                                        <span className="flex-1 min-w-48">
                                            <span className="block text-sm break-words">{b.subject || <span className="text-stone-400">No subject yet</span>}</span>
                                            <span className="block text-[13px] text-stone-500 mt-0.5">{line(b)}</span>
                                            {b.status === "paused" && b.paused_why && <span className="block text-[13px] text-stone-700 mt-0.5">{b.paused_why}</span>}
                                        </span>
                                        <Status tone={s.tone}>{s.label}</Status>
                                    </button>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </Card>
            {earlier.length > 0 && (
                <Card>
                    <div className="px-5 pt-4 pb-3"><h3 className="text-sm font-medium">Earlier bulk emails</h3><p className="text-[13px] text-stone-500 mt-0.5">Sent before November 2026, from the whole workspace.</p></div>
                    <ul>
                        {earlier.map((b) => (
                            <li key={b.id} className="border-t border-line px-5 py-3">
                                <span className="block text-sm break-words">{b.subject}</span>
                                <span className="block text-[13px] text-stone-500 mt-0.5">{line(b)}</span>
                            </li>
                        ))}
                    </ul>
                </Card>
            )}
            {importing && <ImportContacts botId={botId} business={business} onClose={() => setImporting(false)} onDone={() => { void reload(); }} />}
        </div>
    );
}

export default function EmailBulkPage() {
    return <Suspense fallback={<Skeleton className="h-64" />}><BulkPageInner /></Suspense>;
}
