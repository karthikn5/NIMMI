"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, Card, EmptyState, Select, Skeleton, Status, Switch, Textarea, useToast } from "@/components/ui";
import { JourneyEditor } from "@/components/email/JourneyEditor";
import { apiJson } from "@/lib/api";
import type { AssistantEmails, Journey, Journeys, Senders } from "@/lib/email";
import { PlanNeeded, useLimits } from "@/lib/plan";
import { useApi } from "@/lib/useApi";

function summary(j: Journey, page: Journeys) {
    const running = j.counts.active ?? 0, finished = (j.counts.done ?? 0) + (j.counts.stopped ?? 0);
    return [`Starts: ${page.triggers[j.trigger] ?? j.trigger}`, `${j.steps.length} ${j.steps.length === 1 ? "step" : "steps"}`, running ? `${running} on it` : "", finished ? `${finished} finished` : ""].filter(Boolean).join(" · ");
}

function JourneysPage() {
    const toast = useToast();
    const router = useRouter();
    const params = useSearchParams();
    const limits = useLimits();
    const senders = useApi<Senders>("/api/email/senders");
    const [botId, setBotId] = useState("");
    const page = useApi<Journeys>(botId ? `/api/email/journeys?bot_id=${botId}` : null);
    const [wanted, setWanted] = useState("");
    const [busy, setBusy] = useState<string | null>(null);
    const assistants = senders.data?.assistants ?? [];
    const openId = params.get("journey");
    useEffect(() => { if (!botId && assistants[0]) setBotId(assistants[0].bot_id); }, [botId, assistants]);

    const show = (id: string | null) => router.replace(id ? `/dashboard/email/journeys?journey=${id}` : "/dashboard/email/journeys", { scroll: false });
    const make = async (what: string, body: Record<string, string>, path = "/api/email/journeys") => {
        setBusy(what);
        try {
            const made = await apiJson<Journey>(path, { method: "POST", json: { bot_id: botId, ...body } });
            await page.reload();
            setWanted("");
            show(made.id);
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(null);
        }
    };
    const toggle = async (j: Journey, enabled: boolean) => {
        try {
            await apiJson(`/api/email/journeys/${j.id}`, { method: "PUT", json: { name: j.name, trigger: j.trigger, trigger_value: j.trigger_value, goal: j.goal, options: j.options, steps: j.steps, enabled } });
            await page.reload();
        } catch (e) {
            toast((e as Error).message);
        }
    };
    const setCap = async (values: Record<string, number>) => {
        try {
            await apiJson<AssistantEmails>(`/api/email/setup/${botId}`, { method: "PUT", json: { settings: { journeys: values } } });
            await page.reload();
            toast("Saved");
        } catch (e) {
            toast((e as Error).message);
        }
    };

    if (senders.error) return <p className="text-sm text-signal">{senders.error}</p>;
    if (!senders.data) return <Skeleton className="h-64" />;
    if (assistants.length === 0) return <Card className="p-5 text-[13px] text-stone-600">Make an assistant first: journeys belong to it.</Card>;
    if (page.error) return <p className="text-sm text-signal">{page.error}</p>;
    const d = page.data;
    if (!d) return <Skeleton className="h-64" />;
    const plan = limits?.assistant_plans?.[botId];
    const growth = plan ? plan.email_alerts : limits?.includes?.email_alerts ?? true;
    const open = d.items.find((j) => j.id === openId);
    if (open) return <JourneyEditor key={open.id} journey={open} meta={d} onBack={() => show(null)} onChanged={() => { void page.reload(); }} />;
    return (
        <div className="space-y-5">
            {!growth && <PlanNeeded feature="email_alerts" botId={botId}>Get your journeys ready here. They run on Growth or Pro; calls in a journey need Pro.</PlanNeeded>}
            <Card>
                <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4 pb-3">
                    <div className="min-w-0">
                        <h3 className="text-sm font-medium">Journeys</h3>
                        <p className="text-[13px] text-stone-500 mt-0.5">What each lead gets, step by step: emails, WhatsApp, calls and waits. A reply ends it.</p>
                    </div>
                    {assistants.length > 1 && (
                        <Select aria-label="Assistant" className="w-56" value={botId} onChange={(e) => setBotId(e.target.value)}>
                            {assistants.map((a) => <option key={a.bot_id} value={a.bot_id}>{a.bot_name}</option>)}
                        </Select>
                    )}
                </div>
                {d.items.length === 0 ? (
                    <div className="border-t border-line"><EmptyState title="No journeys yet" body="Start from a ready-made one below, or say what you want." /></div>
                ) : (
                    <ul>
                        {d.items.map((j) => (
                            <li key={j.id} className="flex flex-wrap items-center gap-3 px-5 py-3.5 border-t border-line">
                                <button type="button" onClick={() => show(j.id)} className="flex-1 min-w-48 text-left focus-visible:outline-2 focus-visible:outline-plum">
                                    <span className="block text-sm hover:underline">{j.name}</span>
                                    <span className="block text-[13px] text-stone-500 mt-0.5">{summary(j, d)}</span>
                                </button>
                                <Status tone={j.enabled ? "good" : "neutral"}>{j.enabled ? "On" : "Off"}</Status>
                                <Switch checked={j.enabled} onChange={(v) => toggle(j, v)} label={`Turn ${j.name} on`} />
                            </li>
                        ))}
                    </ul>
                )}
            </Card>
            <Card className="p-5">
                <h3 className="text-sm font-medium">Say what you want</h3>
                <p className="text-[13px] text-stone-500 mt-0.5">Nimmi writes the steps, and nothing runs until you check them and turn it on.</p>
                <Textarea aria-label="What the journey should do" className="mt-3" rows={2} maxLength={1000} value={wanted} onChange={(e) => setWanted(e.target.value)}
                          placeholder="Email them now, WhatsApp after 2 hours, call the next morning" />
                <div className="mt-2 flex justify-end">
                    <Button variant="primary" disabled={!!busy || wanted.trim().length < 5} onClick={() => make("write", { text: wanted.trim() }, "/api/email/journeys/write")}>{busy === "write" ? "Writing…" : "Write the steps"}</Button>
                </div>
            </Card>
            <Card>
                <div className="px-5 pt-4 pb-3"><h3 className="text-sm font-medium">Ready-made journeys</h3></div>
                <ul>
                    {d.ready.map((r) => (
                        <li key={r.key} className="flex flex-wrap items-center gap-3 px-5 py-3 border-t border-line">
                            <span className="flex-1 min-w-48">
                                <span className="block text-sm">{r.name}</span>
                                <span className="block text-[13px] text-stone-500 mt-0.5">{r.about}</span>
                            </span>
                            <Button size="sm" disabled={!!busy} aria-label={`Use ${r.name}`} onClick={() => make(r.key, { ready: r.key })}>{busy === r.key ? "Writing…" : "Use this"}</Button>
                        </li>
                    ))}
                </ul>
            </Card>
            <Card className="p-5">
                <h3 className="text-sm font-medium">The most emails one person gets</h3>
                <p className="text-[13px] text-stone-500 mt-0.5">Counts everything you send them, across all journeys. A journey&apos;s next email waits its turn.</p>
                <div className="flex flex-wrap gap-3 mt-3">
                    <Select aria-label="Emails a day" className="w-36" value={d.cap.per_day} onChange={(e) => setCap({ per_day: Number(e.target.value) })}>
                        {[1, 2, 3].map((n) => <option key={n} value={n}>{n} a day</option>)}
                    </Select>
                    <Select aria-label="Emails a week" className="w-36" value={d.cap.per_week} onChange={(e) => setCap({ per_week: Number(e.target.value) })}>
                        {[1, 2, 3, 5, 7].map((n) => <option key={n} value={n}>{n} a week</option>)}
                    </Select>
                </div>
            </Card>
            <Card>
                <div className="px-5 pt-4 pb-3">
                    <h3 className="text-sm font-medium">What else a lead gets</h3>
                    <p className="text-[13px] text-stone-500 mt-0.5">These run on their own, as they always have. If a journey does the same job, turn the older one off, so nobody hears the same thing twice.</p>
                </div>
                <ul>
                    {d.already_running.filter((a) => a.on).map((a) => (
                        <li key={a.name} className="flex items-center justify-between gap-3 px-5 py-2.5 border-t border-line text-sm">
                            <span>{a.name}</span>
                            <Link href={a.where} className="text-[13px] text-plum hover:underline">Open</Link>
                        </li>
                    ))}
                    {!d.already_running.some((a) => a.on) && <li className="px-5 py-3 border-t border-line text-[13px] text-stone-500">None is on.</li>}
                </ul>
            </Card>
        </div>
    );
}

export default function Page() {
    return <Suspense fallback={<Skeleton className="h-64" />}><JourneysPage /></Suspense>;
}
