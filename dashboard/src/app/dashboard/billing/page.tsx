"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Check } from "lucide-react";
import AppHeader from "@/components/AppHeader";
import { BalanceCard, useBalance } from "@/components/Balance";
import { Button, Card, Dialog, EmptyState, SectionHeader, Segmented, Select, Skeleton, Status, ToastProvider, cn, useToast } from "@/components/ui";
import { apiJson, currentUserId } from "@/lib/api";
import { RANK, TIERS, YEARLY_PAYS_FOR, inr, perMonth, priceOf, type Period, type Tier, type TierId } from "@/lib/plans";
import { useLimits } from "@/lib/plan";
import { payAndVerify } from "@/lib/razorpay";
import { formatNumber } from "@/lib/voice/api";
import { RatesTable } from "@/components/voice/RatesTable";
import type { VoiceModels } from "@/lib/voice/types";

/** An assistant's plan (backend payments.py `_plan_json`). */
type Plan = {
    id: string; label: string; tier: TierId | null; period: Period | null; earlier: boolean; price: number;
    starts: string | null; ends: string; renews: boolean; state: "renews" | "ends" | "payment_failed" | "halted";
};
type Assistant = { bot_id: string; name: string; current: Plan | null; next: Plan | null };
type Overview = { assistants: Assistant[]; catalog: { subscriptions: boolean } };
type Quote = { action: "start" | "extend" | "upgrade" | "schedule"; label: string; pay_now: number; starts_at: string; ends_at: string; renews: boolean; note: string };
type Checkout = { description: string } & (
    | { mode: "subscription"; subscription_id: string; key_id: string }
    | { mode: "order"; order_id: string; amount: number; currency: string; key_id: string });
type Payment = { plan_name: string; amount: number; date: string; bot_id: string | null; transaction_id: string };
type Choice = { assistant: Assistant; tier: Tier; period: Period; quote: Quote | null; error: string | null };

/** The backend's times are UTC without a zone. */
const when = (iso: string) => new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
const day = (iso: string) => when(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
const daysLeft = (iso: string) => Math.ceil((when(iso).getTime() - Date.now()) / 86_400_000);

export default function BillingPage() {
    return (
        <ToastProvider>
            <Billing />
        </ToastProvider>
    );
}

function Billing() {
    const router = useRouter();
    const toast = useToast();
    const [overview, setOverview] = useState<Overview | null>(null);
    const [history, setHistory] = useState<Payment[] | null>(null);
    const [credits, setCredits] = useState<number | null>(null);
    const [rates, setRates] = useState<VoiceModels | null>(null);
    const [profile, setProfile] = useState<{ name: string; email: string } | null>(null);
    const [botId, setBotId] = useState("");
    const [period, setPeriod] = useState<Period>("monthly");
    const [choice, setChoice] = useState<Choice | null>(null);
    const [stopping, setStopping] = useState<Assistant | null>(null);
    const [busy, setBusy] = useState(false);
    const wallet = useBalance();
    const limits = useLimits();

    const load = useCallback(async () => {
        try {
            const [o, h] = await Promise.all([apiJson<Overview>("/api/payments/plans"), apiJson<Payment[]>("/api/payments/history")]);
            setOverview(o);
            setHistory(h);
            setBotId((current) => {
                if (current && o.assistants.some((a) => a.bot_id === current)) return current;
                const asked = new URLSearchParams(window.location.search).get("bot");
                return o.assistants.find((a) => a.bot_id === asked)?.bot_id ?? o.assistants.find((a) => !a.current)?.bot_id
                    ?? o.assistants[0]?.bot_id ?? "";
            });
        } catch (e) {
            toast((e as Error).message);
            setOverview((x) => x ?? { assistants: [], catalog: { subscriptions: true } });
            setHistory((x) => x ?? []);
        }
        apiJson<VoiceModels>("/api/voice/models").then(setRates).catch(() => { /* the rates show on the agent page too */ });
        apiJson<{ credits_left: number }>("/api/voice/overview").then((o) => setCredits(o.credits_left)).catch(() => {});
    }, [toast]);

    useEffect(() => {
        if (!currentUserId()) {
            router.push("/auth/login");
            return;
        }
        load();
        apiJson<{ name: string; email: string }>("/api/auth/profile").then(setProfile).catch(() => {});
    }, [router, load]);

    const selected = overview?.assistants.find((a) => a.bot_id === botId);
    const selectedPeriod = selected?.current?.period;
    useEffect(() => {  // show the period the chosen assistant is on
        if (selectedPeriod) setPeriod(selectedPeriod);
    }, [botId, selectedPeriod]);

    const choose = async (tier: Tier) => {
        if (!selected) return toast("Create an assistant first.");
        const asked: Choice = { assistant: selected, tier, period, quote: null, error: null };
        setChoice(asked);
        try {
            const quote = await apiJson<Quote>("/api/payments/quote", { method: "POST", json: { bot_id: selected.bot_id, tier: tier.id, period } });
            setChoice({ ...asked, quote });
        } catch (e) {
            setChoice({ ...asked, error: (e as Error).message });
        }
    };

    const pay = async () => {
        if (!choice?.quote) return;
        setBusy(true);
        let checkout: Checkout;
        try {
            checkout = await apiJson<Checkout>("/api/payments/checkout", {
                method: "POST", json: { bot_id: choice.assistant.bot_id, tier: choice.tier.id, period: choice.period } });
        } catch (e) {  // couldn't start: say why where they're looking
            setChoice((c) => (c ? { ...c, error: (e as Error).message } : c));
            setBusy(false);
            return;
        }
        setChoice(null);
        try {
            const done = await payAndVerify(checkout.mode === "subscription"
                ? { subscription_id: checkout.subscription_id, key_id: checkout.key_id }
                : { order_id: checkout.order_id, amount: checkout.amount, currency: checkout.currency, key_id: checkout.key_id },
                { description: checkout.description, email: profile?.email, name: profile?.name });
            if (done) toast(done.message);
            await load();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    const stopRenewing = async () => {
        if (!stopping) return;
        setBusy(true);
        try {
            const r = await apiJson<{ message: string }>("/api/payments/stop-renewal", { method: "POST", json: { bot_id: stopping.bot_id } });
            toast(r.message);
            setStopping(null);
            await load();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    const updateCard = async (a: Assistant) => {
        try {
            const r = await apiJson<{ subscription_id: string; key_id: string; description: string }>(
                "/api/payments/update-card", { method: "POST", json: { bot_id: a.bot_id } });
            const done = await payAndVerify({ ...r, card_change: true }, { description: r.description, email: profile?.email, name: profile?.name });
            if (done) toast(done.message);
            await load();
        } catch (e) {
            toast((e as Error).message);
        }
    };

    const pick = (a: Assistant) => {
        setBotId(a.bot_id);
        document.getElementById("plans")?.scrollIntoView({ behavior: "smooth", block: "start" });
    };

    const names = useMemo(() => {
        const seen = new Map<string, number>();
        for (const a of overview?.assistants ?? []) seen.set(a.name, (seen.get(a.name) ?? 0) + 1);
        return (a: Assistant) => ((seen.get(a.name) ?? 0) > 1 ? `${a.name} (${a.bot_id.slice(0, 8)})` : a.name);
    }, [overview]);

    return (
        <div className="min-h-screen bg-paper text-ink">
            <AppHeader />
            <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 pb-24">
                <h1 className="text-2xl font-semibold tracking-tight">Billing</h1>
                <p className="text-sm text-stone-500 mt-1">Plans are per assistant. An assistant answers your customers while it has a plan.</p>

                <section className="mt-8">
                    <SectionHeader title="Your assistants" />
                    <Card>
                        {overview === null ? (
                            <div className="p-5 space-y-3"><Skeleton className="h-12" /><Skeleton className="h-12" /></div>
                        ) : !overview.assistants.length ? (
                            <EmptyState title="No assistants yet" body="Create an assistant, then choose a plan for it here."
                                        action={<Link href="/dashboard"><Button size="sm">Go to assistants</Button></Link>} />
                        ) : (
                            <ul>
                                {overview.assistants.map((a) => (
                                    <AssistantRow key={a.bot_id} a={a} name={names(a)} onPick={() => pick(a)} onStop={() => setStopping(a)}
                                                  onCard={() => updateCard(a)} usage={limits?.assistant_plans?.[a.bot_id]} />
                                ))}
                            </ul>
                        )}
                    </Card>
                </section>

                <section id="plans" className="mt-10 scroll-mt-6">
                    <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-3 mb-4">
                        <div>
                            <h2 className="text-[15px] font-semibold">Plans</h2>
                            <p className="text-[13px] text-stone-500 mt-0.5">Per assistant. Yearly is 12 months for the price of {YEARLY_PAYS_FOR}.</p>
                        </div>
                        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                            <label className="flex items-center gap-2 text-[13px] text-stone-600">
                                For
                                {overview === null ? <Skeleton className="h-9 w-56" /> : (
                                    <Select aria-label="Assistant" className="w-56" value={botId} onChange={(e) => setBotId(e.target.value)}
                                            disabled={!overview.assistants.length}>
                                        {!overview.assistants.length && <option>No assistants yet</option>}
                                        {overview.assistants.map((a) => <option key={a.bot_id} value={a.bot_id}>{names(a)}</option>)}
                                    </Select>
                                )}
                            </label>
                            <Segmented label="Billing period" value={period} onChange={setPeriod}
                                       options={[{ value: "monthly", label: "Monthly" }, { value: "yearly", label: "Yearly, 2 months free" }]} />
                        </div>
                    </div>

                    <div className="grid gap-4 md:grid-cols-3">
                        {TIERS.map((tier) => (
                            <TierCard key={tier.id} tier={tier} period={period} current={selected?.current ?? null}
                                      subscriptions={overview?.catalog.subscriptions ?? true}
                                      disabled={!selected || busy} onChoose={() => choose(tier)} />
                        ))}
                    </div>
                    <p className="text-[12.5px] text-stone-500 mt-4 max-w-3xl leading-relaxed">
                        Monthly plans renew by themselves; stop any time and the plan runs to its end date. Yearly plans are paid
                        once a year, with reminders before they end. An upgrade starts at once: you pay the difference for the days
                        left. Other changes start when the current period ends. Phone calls use call credits, on every plan.
                    </p>
                </section>

                <div className="grid gap-6 lg:grid-cols-3 mt-10">
                    <section className="lg:col-span-2 min-w-0" id="rates">
                        <SectionHeader title="Call rates"
                                       description="What a call minute costs on each AI model. Choose the model on each agent's page, under Voice > Agents." />
                        {rates ? <RatesTable card={rates} /> : <Skeleton className="h-72" />}
                    </section>
                    <section className="min-w-0">
                        <SectionHeader title="Call credits" />
                        <Card className="p-5">
                            <p className="tabular-nums">
                                <span className="text-[28px] leading-none font-semibold tracking-tight">{credits === null ? "–" : formatNumber(credits)}</span>
                                <span className="text-sm text-stone-500"> credits left</span>
                            </p>
                            <p className="text-[13px] text-stone-500 mt-2">
                                Pay as you go for phone calls and test calls. A call minute is 1 credit for the voice and phone line,
                                plus the agent&apos;s AI model (see Call rates). Pro includes 300 credits a month. Credits don&apos;t expire.
                            </p>
                            <Link href="/dashboard/voice" className="inline-flex items-center gap-1 mt-4 text-[13px] text-plum hover:underline underline-offset-4">
                                Buy credits <ArrowRight size={13} />
                            </Link>
                        </Card>
                    </section>
                </div>

                {wallet.data && (
                    <section className="mt-10">
                        <SectionHeader
                            title="Nimmi balance"
                            description="Prepaid money for phone numbers. Each number's monthly fee is taken from here; if the balance runs out, the number pauses until you add more."
                        />
                        <BalanceCard info={wallet} showActivity />
                    </section>
                )}

                <section className="mt-10">
                    <SectionHeader title="Payment history" />
                    <Card>
                        {history === null ? (
                            <div className="p-5"><Skeleton className="h-10" /></div>
                        ) : !history.length ? (
                            <EmptyState title="No payments yet" body="Payments for plans and call credits show up here." />
                        ) : (
                            <table className="w-full text-sm">
                                <thead className="hidden sm:table-header-group">
                                    <tr className="text-left text-[13px] text-stone-500">
                                        <th className="font-normal px-5 py-3">Date</th>
                                        <th className="font-normal px-3 py-3">Item</th>
                                        <th className="font-normal px-3 py-3">Assistant</th>
                                        <th className="font-normal px-3 py-3 text-right">Amount</th>
                                        <th className="font-normal px-3 py-3 text-right">Payment ID</th>
                                        <th className="font-normal px-5 py-3 text-right"><span className="sr-only">Receipt</span></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {history.map((p) => (
                                        <tr key={p.transaction_id} className="border-t border-line first:border-t-0 sm:first:border-t">
                                            <td className="px-5 py-3 text-stone-600 whitespace-nowrap">{p.date}</td>
                                            <td className="px-3 py-3">{p.plan_name}</td>
                                            <td className="hidden sm:table-cell px-3 py-3 text-stone-600">
                                                {overview?.assistants.find((a) => a.bot_id === p.bot_id)?.name ?? "–"}
                                            </td>
                                            <td className="px-3 py-3 text-right tabular-nums">{inr(p.amount)}</td>
                                            <td className="hidden sm:table-cell px-3 py-3 text-right text-xs text-stone-400 font-mono">{p.transaction_id}</td>
                                            <td className="px-5 py-3 text-right">
                                                <Link href={`/dashboard/billing/receipt/${encodeURIComponent(p.transaction_id)}`}
                                                      className="text-[13px] text-plum hover:underline underline-offset-4">Receipt</Link>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </Card>
                </section>
            </main>

            <Dialog open={!!choice} onClose={() => !busy && setChoice(null)}
                    title={choice ? `${choice.quote?.label ?? `${choice.tier.name} ${choice.period}`} for ${names(choice.assistant)}` : ""}
                    footer={choice && (
                        <>
                            <Button variant="ghost" onClick={() => setChoice(null)} disabled={busy}>{choice.error ? "Close" : "Cancel"}</Button>
                            {!choice.error && (
                                <Button variant="primary" onClick={pay} disabled={!choice.quote || busy}>
                                    {busy ? "Opening payment…" : choice.quote && choice.quote.pay_now > 0 ? `Pay ${inr(choice.quote.pay_now)}` : "Set it up"}
                                </Button>
                            )}
                        </>
                    )}>
                {choice?.error ? (
                    <p className="text-[13px] text-stone-700">{choice.error}</p>
                ) : !choice?.quote ? (
                    <div className="space-y-2"><Skeleton className="h-4" /><Skeleton className="h-4 w-2/3" /></div>
                ) : (
                    <div className="space-y-3 text-[13.5px]">
                        <p className="text-stone-700 leading-relaxed">{choice.quote.note}</p>
                        {choice.quote.pay_now === 0 && choice.quote.renews && (
                            <p className="text-[12.5px] text-stone-500">Nothing to pay now. Razorpay checks your card or UPI with ₹5 and refunds it at once.</p>
                        )}
                        {choice.quote.renews && (
                            <p className="text-[12.5px] text-stone-500">It renews by itself each month until you stop it on this page.</p>
                        )}
                    </div>
                )}
            </Dialog>

            <Dialog open={!!stopping} onClose={() => !busy && setStopping(null)}
                    title={stopping ? (stopping.next?.renews ? `Cancel the change to ${stopping.next.label}?` : `Stop renewing ${stopping.current?.label ?? "the plan"}?`) : ""}
                    footer={stopping && (
                        <>
                            <Button variant="ghost" onClick={() => setStopping(null)} disabled={busy}>Keep it</Button>
                            <Button variant="danger" onClick={stopRenewing} disabled={busy}>
                                {busy ? "Stopping…" : stopping.next?.renews ? "Cancel the change" : "Stop renewing"}
                            </Button>
                        </>
                    )}>
                {stopping?.current && (
                    <p className="text-[13.5px] text-stone-700 leading-relaxed">
                        {names(stopping)} keeps {stopping.current.label} until {day(stopping.current.ends)}. After that it stops answering
                        customers, unless you choose a plan again.
                    </p>
                )}
            </Dialog>
        </div>
    );
}

function AssistantRow({ a, name, onPick, onStop, onCard, usage }: {
    a: Assistant; name: string; onPick: () => void; onStop: () => void; onCard: () => void;
    usage?: { replies: number | null; replies_used: number };
}) {
    const c = a.current;
    const soon = c && !c.renews && daysLeft(c.ends) <= 7;
    const allowed = c ? usage?.replies ?? null : null;  // AI replies its plan includes this month (earlier plans: no limit)
    const used = usage?.replies_used ?? 0;
    return (
        <li className="flex flex-col gap-2 sm:grid sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_auto] sm:gap-x-5 sm:items-center px-5 py-3.5 border-t border-line first:border-t-0">
            <div className="min-w-0">
                <p className="text-sm font-medium truncate">{name}</p>
                <p className="text-xs text-stone-400 truncate">{c ? c.label : "No plan"}{c?.earlier ? ", everything included" : ""}</p>
            </div>
            <div className="text-[13px] min-w-0">
                {!c ? <Status tone="neutral">Not answering customers</Status>
                    : c.state === "payment_failed" ? <Status tone="warn">Payment failed. Razorpay tries again for 3 days</Status>
                    : c.state === "halted" ? <Status tone="bad">Renewal stopped after a failed payment. Ends on {day(c.ends)}</Status>
                    : c.state === "renews" ? <Status tone="good">Renews on {day(c.ends)}</Status>
                    : <Status tone={soon ? "warn" : "good"}>Ends on {day(c.ends)}</Status>}
                {a.next && <p className="text-xs text-stone-500 mt-1">Then {a.next.label} from {day(a.next.starts ?? a.next.ends)}</p>}
                {allowed !== null && (
                    <p className={cn("text-xs mt-1 tabular-nums", used >= allowed ? "text-signal" : used >= allowed * 0.8 ? "text-amber-700" : "text-stone-500")}>
                        {used >= allowed ? `All ${allowed.toLocaleString("en-IN")} AI replies used this month: it answers again on the 1st, or at once with a bigger plan`
                            : `${used.toLocaleString("en-IN")} of ${allowed.toLocaleString("en-IN")} AI replies this month`}
                    </p>
                )}
            </div>
            <div className="flex flex-wrap gap-2 sm:justify-end">
                {c && (c.state === "payment_failed" || c.state === "halted") && <Button size="sm" variant="primary" onClick={onCard}>Update payment method</Button>}
                <Button size="sm" onClick={onPick}>{!c ? "Choose a plan" : c.earlier ? "Choose next plan" : "Change plan"}</Button>
                {(c?.renews || a.next?.renews) && (
                    <Button size="sm" variant="ghost" onClick={onStop}>{a.next?.renews ? "Cancel the change" : "Stop renewing"}</Button>
                )}
            </div>
        </li>
    );
}

function TierCard({ tier, period, current, subscriptions, disabled, onChoose }: {
    tier: Tier; period: Period; current: Plan | null; subscriptions: boolean; disabled: boolean; onChoose: () => void;
}) {
    const same = !!current && !current.earlier && current.tier === tier.id && current.period === period;
    let cta = `Choose ${tier.name}`;
    if (current && !current.earlier && current.tier) {
        if (same) cta = current.renews ? "Current plan" : period === "yearly" ? "Renew for a year" : "Renew monthly";
        else if (current.tier === tier.id) cta = `Switch to ${period}`;
        else if (current.period === period && RANK[tier.id] > RANK[current.tier]) cta = `Upgrade to ${tier.name}`;
        else cta = `Switch to ${tier.name}`;
    }
    const isCurrent = same && current?.renews;
    return (
        <Card className={cn("p-5 flex flex-col", tier.featured && "border-plum ring-1 ring-plum", same && "bg-plum-tint/40")}>
            <div className="flex items-baseline justify-between gap-2">
                <h3 className="text-sm font-semibold">{tier.name}</h3>
                {same ? <span className="text-xs text-plum font-medium">Current plan</span>
                    : tier.featured && <span className="text-xs text-plum font-medium">Recommended</span>}
            </div>
            <p className="text-[13px] text-stone-600 mt-1">{tier.summary}</p>
            <p className="mt-4 flex items-baseline gap-1.5">
                <span className="text-3xl font-semibold tracking-tight tabular-nums">{inr(perMonth(tier, period))}</span>
                <span className="text-sm text-stone-500">a month</span>
            </p>
            <p className="text-xs text-stone-500 mt-1 h-4">
                {period === "yearly" ? `${inr(priceOf(tier, "yearly"))} billed yearly` : subscriptions ? "Billed monthly, renews by itself" : "Billed monthly"}
            </p>
            <p className="text-[12.5px] font-medium mt-5 mb-2">{tier.previous ? `Everything in ${tier.previous}, plus` : "Includes"}</p>
            <ul className="space-y-2 text-[13px] flex-1">
                {tier.includes.map((f) => (
                    <li key={f} className="flex gap-2"><Check size={14} className="mt-0.5 text-plum shrink-0" aria-hidden />{f}</li>
                ))}
            </ul>
            <Button variant={tier.featured && !isCurrent ? "primary" : "secondary"} className="mt-5 w-full" disabled={disabled || !!isCurrent}
                    onClick={onChoose}>
                {cta}
            </Button>
        </Card>
    );
}
