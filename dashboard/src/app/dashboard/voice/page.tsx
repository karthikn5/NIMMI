"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Check, PhoneIncoming, PhoneOutgoing } from "lucide-react";
import DailyChart from "@/components/DailyChart";
import { Button, Card, Dialog, EmptyState, Notice, Skeleton, Status, cn, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { payAndVerify } from "@/lib/razorpay";
import { useApi } from "@/lib/useApi";
import { OUTCOMES, formatDate, formatDuration, formatINR, formatNumber, formatRate, formatWhen } from "@/lib/voice/api";
import type { CallRecord, VoiceModels, VoiceOverview } from "@/lib/voice/types";

export default function VoiceOverviewPage() {
    const overview = useApi<VoiceOverview>("/api/voice/overview");
    const calls = useApi<CallRecord[]>("/api/voice/calls?limit=5");

    if (overview.loading) return <OverviewSkeleton />;
    if (overview.error || !overview.data) {
        return <p className="text-sm text-signal">Couldn&apos;t load voice overview. {overview.error}</p>;
    }

    const o = overview.data;
    const change = o.calls_last_month ? Math.round(((o.calls_this_month - o.calls_last_month) / o.calls_last_month) * 100) : null;

    return (
        <>
            {!o.engine_ready && (
                <Notice title="Voice engine not connected">
                    Test calls and phone calls start working once the server has a Sarvam API key. Everything else here is live.
                </Notice>
            )}

            <Card className="grid grid-cols-2 lg:grid-cols-4 [&>*]:border-line">
                <Metric
                    label="Calls this month"
                    value={formatNumber(o.calls_this_month)}
                    note={change === null ? undefined : `${change >= 0 ? "+" : ""}${change}% vs last month`}
                />
                <Metric label="Handled without a person" value={`${o.ai_resolved_pct}%`} note="Not transferred or dropped" className="border-l" />
                <Metric label="Average call" value={o.avg_duration_sec ? `${Math.floor(o.avg_duration_sec / 60)}m ${o.avg_duration_sec % 60}s` : "–"} note="Calls that connected" className="border-t lg:border-t-0 lg:border-l" />
                <Metric label="Leads captured" value={formatNumber(o.leads_captured)} note="Name and number collected" className="border-t border-l lg:border-t-0" />
            </Card>

            <div className="grid gap-6 lg:grid-cols-3 mt-6">
                <Card className="lg:col-span-2 p-5">
                    <div className="flex items-baseline justify-between mb-4">
                        <h2 className="text-[15px] font-semibold">Calls per day</h2>
                        <span className="text-[13px] text-stone-500">Last 14 days</span>
                    </div>
                    <DailyChart data={o.calls_by_day} unit="call" />
                </Card>
                <CreditsCard overview={o} onBought={overview.reload} />
            </div>

            <div className="grid gap-6 lg:grid-cols-3 mt-6">
                <Card className="lg:col-span-2">
                    <div className="flex items-center justify-between px-5 pt-5 pb-3">
                        <h2 className="text-[15px] font-semibold">Recent calls</h2>
                        <Link href="/dashboard/voice/calls" className="text-[13px] text-plum hover:underline underline-offset-4 inline-flex items-center gap-1">
                            All calls <ArrowRight size={13} />
                        </Link>
                    </div>
                    {calls.loading ? (
                        <div className="px-5 pb-5 space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}</div>
                    ) : !calls.data?.length ? (
                        <EmptyState title="No calls yet" body="Calls show up here as soon as your assistant answers one. Start with a test call from an agent's page." />
                    ) : (
                        <ul>
                            {calls.data.map((c) => (
                                <li key={c.id}>
                                    <Link
                                        href={`/dashboard/voice/calls?call=${c.id}`}
                                        className="grid grid-cols-[16px_minmax(0,1fr)_auto] sm:grid-cols-[16px_minmax(0,1fr)_9rem_3rem_7.5rem] items-center gap-x-3 gap-y-0.5 px-5 py-3 border-t border-line hover:bg-stone-50 transition-colors"
                                    >
                                        {c.direction === "inbound"
                                            ? <PhoneIncoming size={14} className="text-stone-400" aria-label="Inbound" />
                                            : <PhoneOutgoing size={14} className="text-stone-400" aria-label="Outbound" />}
                                        <div className="min-w-0">
                                            <p className="text-sm tabular-nums truncate">{c.caller}</p>
                                            <p className="text-xs text-stone-500 truncate">{c.bot_name}</p>
                                        </div>
                                        <div className="hidden sm:block"><Status tone={OUTCOMES[c.outcome].tone}>{OUTCOMES[c.outcome].label}</Status></div>
                                        <span className="hidden sm:block text-[13px] text-stone-500 tabular-nums text-right">{formatDuration(c.duration_sec)}</span>
                                        <span className="text-xs text-stone-500 text-right whitespace-nowrap">{formatWhen(c.started_at)}</span>
                                    </Link>
                                </li>
                            ))}
                        </ul>
                    )}
                </Card>
                <SetupCard setup={o.setup} />
            </div>
        </>
    );
}

function Metric({ label, value, note, className }: { label: string; value: string; note?: string; className?: string }) {
    return (
        <div className={cn("p-5", className)}>
            <p className="text-[13px] text-stone-500">{label}</p>
            <p className="text-[28px] leading-none font-semibold tracking-tight tabular-nums mt-3">{value}</p>
            {note && <p className="text-xs text-stone-500 mt-2">{note}</p>}
        </div>
    );
}

function CreditsCard({ overview: o, onBought }: { overview: VoiceOverview; onBought: () => void }) {
    const [open, setOpen] = useState(false);
    const out = o.credits_left < 0.5;  // less than a half-minute
    const low = !out && o.credits_left < 5;

    return (
        <Card className="p-5 flex flex-col">
            <h2 className="text-[15px] font-semibold">Credits</h2>
            <p className="mt-4 tabular-nums">
                <span className="text-[28px] leading-none font-semibold tracking-tight">{formatNumber(o.credits_left)}</span>
                <span className="text-sm text-stone-500"> credits left</span>
            </p>
            <p className="text-[13px] text-stone-500 mt-2 leading-relaxed">
                A call minute is 1 credit for the voice and phone line, plus the agent&apos;s AI model.
                Calls are counted in half-minutes. <Link href="/dashboard/billing#rates" className="text-plum hover:underline">Call rates</Link>
            </p>
            <dl className="mt-4 text-[13px] space-y-1.5">
                {o.credits_included > 0 && (
                    <div className="flex justify-between gap-3"><dt className="text-stone-500">Plan credits used</dt><dd className="tabular-nums">{formatNumber(o.credits_used)} of {formatNumber(o.credits_included)}</dd></div>
                )}
                {o.credits_included > 0 && o.cycle_ends && (
                    <div className="flex justify-between gap-3"><dt className="text-stone-500">Plan credits reset</dt><dd>{formatDate(o.cycle_ends)}</dd></div>
                )}
                <div className="flex justify-between gap-3"><dt className="text-stone-500">Bought and free credits</dt><dd className="tabular-nums">{formatNumber(o.credits_bought)}</dd></div>
            </dl>
            {out && <p className="mt-3 text-[13px] text-signal">Calls are paused until you add credits.</p>}
            {low && <p className="mt-3 text-[13px] text-amber-700">Running low. Calls stop when the credits run out.</p>}
            <div className="mt-auto pt-5">
                <Button className="w-full" variant={out || low ? "primary" : undefined} onClick={() => setOpen(true)}>Buy credits</Button>
            </div>
            <BuyCreditsDialog open={open} onClose={() => setOpen(false)} onBought={onBought} />
        </Card>
    );
}

function BuyCreditsDialog({ open, onClose, onBought }: { open: boolean; onClose: () => void; onBought: () => void }) {
    const toast = useToast();
    const rates = useApi<VoiceModels>(open ? "/api/voice/models" : null);
    const [selected, setSelected] = useState<string>("p_500");
    const [busy, setBusy] = useState(false);
    const chosen = rates.data?.packs.find((p) => p.id === selected);
    const usual = rates.data?.models.find((m) => m.id === rates.data?.default);

    const checkout = async () => {
        setBusy(true);
        try {
            const order = await apiJson<{ order_id: string; amount: number; currency: string; key_id: string; credits: number }>(
                "/api/payments/create-minutes-order", { method: "POST", json: { pack_id: selected } });
            onClose();
            const result = await payAndVerify(order, { description: `${formatNumber(order.credits)} voice credits` });
            if (result) {
                toast(result.message);
                onBought();
            }
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    return (
        <Dialog
            open={open}
            onClose={onClose}
            title="Buy credits"
            description="Pay as you go: credits never expire and are used after any plan credits. You pay the price shown."
            footer={<>
                <Button variant="ghost" onClick={onClose}>Cancel</Button>
                <Button variant="primary" onClick={checkout} disabled={busy}>{busy ? "Opening payment…" : "Continue to payment"}</Button>
            </>}
        >
            <fieldset className="space-y-2">
                <legend className="sr-only">Credit packs</legend>
                {(rates.data?.packs ?? []).map((p) => (
                    <label
                        key={p.id}
                        className={cn(
                            "flex items-center gap-3 px-4 py-3 rounded-md border cursor-pointer transition-colors",
                            selected === p.id ? "border-plum bg-plum-tint" : "border-line hover:border-line-strong",
                        )}
                    >
                        <input type="radio" name="pack" value={p.id} checked={selected === p.id} onChange={() => setSelected(p.id)} className="accent-plum" />
                        <span className="flex-1 text-sm font-medium tabular-nums">{formatNumber(p.credits)} credits</span>
                        <span className="text-right">
                            <span className="block text-sm tabular-nums">{formatINR(p.price)}</span>
                            <span className="block text-xs text-stone-500 tabular-nums">₹{(p.price / p.credits).toFixed(2)} a credit</span>
                        </span>
                    </label>
                ))}
            </fieldset>
            {chosen && usual && (
                <p className="text-xs text-stone-500 mt-3 leading-relaxed">
                    About {formatNumber(Math.floor(chosen.credits / usual.credits_per_minute))} minutes of calls on {usual.name},
                    at {formatRate(usual.credits_per_minute)} credits a minute. Smarter models use more.
                </p>
            )}
        </Dialog>
    );
}

function SetupCard({ setup }: { setup: VoiceOverview["setup"] }) {
    const steps = [
        { done: setup.voice_chosen, title: "Choose a voice", body: "Pick a language and voice for an assistant.", href: "/dashboard/voice/agents" },
        { done: setup.tested_in_browser, title: "Talk to it in your browser", body: "Hear how it answers before customers do.", href: "/dashboard/voice/agents" },
        { done: setup.number_active, title: "Get a phone number", body: "Customers call this number to reach your assistant.", href: "/dashboard/voice/numbers" },
        { done: setup.callbacks_on, title: "Call back new leads", body: "Ring people who ask for a callback in chat.", href: "/dashboard/voice/numbers#callbacks" },
    ];
    const doneCount = steps.filter((s) => s.done).length;

    return (
        <Card className="p-5">
            <div className="flex items-baseline justify-between">
                <h2 className="text-[15px] font-semibold">Setup</h2>
                <span className="text-[13px] text-stone-500 tabular-nums">{doneCount} of {steps.length} done</span>
            </div>
            <ol className="mt-4 space-y-1">
                {steps.map((s, i) => (
                    <li key={s.title}>
                        <Link href={s.href} className="flex gap-3 p-2 -mx-2 rounded-md hover:bg-stone-50 transition-colors">
                            <span className={cn(
                                "mt-0.5 h-5 w-5 shrink-0 rounded-full flex items-center justify-center text-[11px] tabular-nums",
                                s.done ? "bg-plum-tint text-plum" : "border border-line-strong text-stone-500",
                            )}>
                                {s.done ? <Check size={12} strokeWidth={2.5} aria-label="Done" /> : i + 1}
                            </span>
                            <span>
                                <span className={cn("block text-sm", s.done ? "text-stone-500" : "font-medium")}>{s.title}</span>
                                {!s.done && <span className="block text-[13px] text-stone-500 mt-0.5">{s.body}</span>}
                            </span>
                        </Link>
                    </li>
                ))}
            </ol>
        </Card>
    );
}

function OverviewSkeleton() {
    return (
        <div className="space-y-6">
            <Skeleton className="h-[116px]" />
            <div className="grid gap-6 lg:grid-cols-3">
                <Skeleton className="h-64 lg:col-span-2" />
                <Skeleton className="h-64" />
            </div>
        </div>
    );
}
