"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AppHeader from "@/components/AppHeader";
import DailyChart from "@/components/DailyChart";
import { Card, EmptyState, Segmented, Select, Skeleton, cn } from "@/components/ui";
import { currentUserId } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { formatNumber } from "@/lib/voice/api";

type Totals = { conversations: number; messages: number; leads: number; handoffs: number; calls: number; call_leads: number };
type Day = { date: string; conversations: number; leads: number; calls: number };
type BotRow = { bot_id: string; bot_name: string; conversations: number; leads: number; handoffs: number; calls: number };
type Analytics = { days: number; totals: Totals; previous: { conversations: number; leads: number }; by_day: Day[]; by_bot: BotRow[] };
type Metric = "conversations" | "leads" | "calls";

const UNIT: Record<Metric, string> = { conversations: "conversation", leads: "lead", calls: "call" };

function change(now: number, before: number) {
    if (!before) return null;
    const pct = Math.round(((now - before) / before) * 100);
    return `${pct >= 0 ? "+" : ""}${pct}% vs previous period`;
}

export default function AnalyticsPage() {
    const router = useRouter();
    const [days, setDays] = useState("30");
    const [botId, setBotId] = useState("");
    const [metric, setMetric] = useState<Metric>("conversations");
    const data = useApi<Analytics>(`/api/analytics?days=${days}${botId ? `&bot_id=${botId}` : ""}`);
    const bots = useApi<{ id: string; name: string }[]>("/api/bots");

    useEffect(() => { if (!currentUserId()) router.push("/auth/login"); }, [router]);

    const t = data.data?.totals;
    const conversionPct = t && t.conversations ? Math.round((t.leads / t.conversations) * 100) : 0;

    return (
        <div className="min-h-screen bg-paper text-ink">
            <AppHeader />
            <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 pb-24">
                <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
                    <div>
                        <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
                        <p className="text-sm text-stone-500 mt-1">How your assistants are doing, from real conversations and calls.</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                        <Select aria-label="Assistant" className="w-48" value={botId} onChange={(e) => setBotId(e.target.value)}>
                            <option value="">All assistants</option>
                            {(bots.data ?? []).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                        </Select>
                        <Segmented label="Period" value={days} onChange={setDays}
                                   options={[{ value: "7", label: "7 days" }, { value: "30", label: "30 days" }, { value: "90", label: "90 days" }]} />
                    </div>
                </div>

                {data.error && <p className="mt-6 text-sm text-signal">Couldn&apos;t load analytics. {data.error}</p>}

                {!data.data ? (
                    <div className="space-y-6 mt-8"><Skeleton className="h-28" /><Skeleton className="h-72" /></div>
                ) : (
                    <>
                        <Card className="mt-8 grid grid-cols-2 lg:grid-cols-4 [&>*]:border-line">
                            <Stat label="Conversations" value={formatNumber(t!.conversations)} note={change(t!.conversations, data.data.previous.conversations) ?? `${formatNumber(t!.messages)} messages`} />
                            <Stat label="Leads from chat" value={formatNumber(t!.leads)} note={`${conversionPct}% of conversations`} className="border-l" />
                            <Stat label="Asked for a person" value={formatNumber(t!.handoffs)} note="Handed to live chat" className="border-t lg:border-t-0 lg:border-l" />
                            <Stat label="Phone calls" value={formatNumber(t!.calls)} note={`${formatNumber(t!.call_leads)} became leads`} className="border-t border-l lg:border-t-0" />
                        </Card>

                        <Card className="mt-6 p-5">
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                                <h2 className="text-[15px] font-semibold">Per day</h2>
                                <Segmented label="Metric" value={metric} onChange={setMetric}
                                           options={[{ value: "conversations", label: "Conversations" }, { value: "leads", label: "Leads" }, { value: "calls", label: "Calls" }]} />
                            </div>
                            <DailyChart key={metric + days} unit={UNIT[metric]} data={data.data.by_day.map((d) => ({ date: d.date, count: d[metric] }))} />
                        </Card>

                        <section className="mt-6">
                            <Card>
                                <div className="px-5 pt-5 pb-3"><h2 className="text-[15px] font-semibold">By assistant</h2></div>
                                {data.data.by_bot.length === 0 ? (
                                    <EmptyState title="No activity in this period" body="Conversations and calls appear here as visitors use your assistants." />
                                ) : (
                                    <table className="w-full text-sm">
                                        <thead>
                                            <tr className="text-left text-[13px] text-stone-500 border-t border-line">
                                                <th className="font-normal px-5 py-2.5">Assistant</th>
                                                <th className="font-normal px-3 py-2.5 text-right">Conversations</th>
                                                <th className="font-normal px-3 py-2.5 text-right">Leads</th>
                                                <th className="hidden sm:table-cell font-normal px-3 py-2.5 text-right">Handoffs</th>
                                                <th className="hidden sm:table-cell font-normal px-5 py-2.5 text-right">Calls</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {data.data.by_bot.map((b) => (
                                                <tr key={b.bot_id} className="border-t border-line">
                                                    <td className="px-5 py-3 font-medium">{b.bot_name}</td>
                                                    <td className="px-3 py-3 text-right tabular-nums">{formatNumber(b.conversations)}</td>
                                                    <td className="px-3 py-3 text-right tabular-nums">{formatNumber(b.leads)}</td>
                                                    <td className="hidden sm:table-cell px-3 py-3 text-right tabular-nums">{formatNumber(b.handoffs)}</td>
                                                    <td className="hidden sm:table-cell px-5 py-3 text-right tabular-nums">{formatNumber(b.calls)}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                )}
                            </Card>
                        </section>
                    </>
                )}
            </main>
        </div>
    );
}

function Stat({ label, value, note, className }: { label: string; value: string; note?: string; className?: string }) {
    return (
        <div className={cn("p-5", className)}>
            <p className="text-[13px] text-stone-500">{label}</p>
            <p className="text-[28px] leading-none font-semibold tracking-tight tabular-nums mt-3">{value}</p>
            {note && <p className="text-xs text-stone-500 mt-2">{note}</p>}
        </div>
    );
}
