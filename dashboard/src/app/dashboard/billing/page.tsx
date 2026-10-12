"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Check } from "lucide-react";
import AppHeader from "@/components/AppHeader";
import { BalanceCard, useBalance } from "@/components/Balance";
import { Button, Card, EmptyState, SectionHeader, Select, Skeleton, Status, Switch, ToastProvider, cn, useToast } from "@/components/ui";
import { apiJson, currentUserId } from "@/lib/api";
import { payAndVerify } from "@/lib/razorpay";
import { formatNumber } from "@/lib/voice/api";

const PLANS = [
    {
        name: "1 Month Plan", label: "1 month", price: 1, originalPrice: 299, perMonth: "₹1 a month",
        description: "Try Nimmi AI on one assistant.",
        features: ["Full access for 1 assistant", "Unlimited conversations", "Train on PDFs and text", "Export code unlocked", "Standard response time"],
    },
    {
        name: "6 Month Plan", label: "6 months", price: 499, originalPrice: 1499, perMonth: "₹83 a month", popular: true,
        description: "For assistants you rely on every day.",
        features: ["Full access for 1 assistant", "Unlimited conversations", "Train on website URLs", "Export code unlocked", "Fast response time", "Priority support"],
    },
    {
        name: "12 Month Plan", label: "12 months", price: 999, originalPrice: 2599, perMonth: "₹83 a month",
        description: "The lowest price over a year.",
        features: ["Full access for 1 assistant", "Unlimited conversations", "Auto-sync data source", "Export code unlocked", "Lightning fast API", "API access"],
    },
];

type Bot = { id: string; name: string; status: "Active" | "Expired"; plan: string; expiry: string; days_remaining: number };
type Sub = { bot_id: string; plan_name: string; status: "active" | "expired"; end_date: string; days_remaining: number; auto_renewal: boolean };
type Payment = { plan_name: string; amount: number; date: string; bot_id: string | null; transaction_id: string };

const inr = (n: number) => `₹${formatNumber(n)}`;

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
    const [bots, setBots] = useState<Bot[] | null>(null);
    const [subs, setSubs] = useState<Sub[]>([]);
    const [history, setHistory] = useState<Payment[] | null>(null);
    const [minutes, setMinutes] = useState<number | null>(null);
    const [botId, setBotId] = useState("");
    const [paying, setPaying] = useState<string | null>(null);
    const [profile, setProfile] = useState<{ name: string; email: string } | null>(null);
    const wallet = useBalance();

    const load = useCallback(async () => {
        try {
            const [b, s, h] = await Promise.all([
                apiJson<Bot[]>("/api/bots"),
                apiJson<Sub[]>("/api/payments/subscriptions"),
                apiJson<Payment[]>("/api/payments/history"),
            ]);
            setBots(b);
            setSubs(s);
            setHistory(h);
            setBotId((current) => {
                if (current && b.some((x) => x.id === current)) return current;
                const requested = new URLSearchParams(window.location.search).get("bot");
                return b.find((x) => x.id === requested)?.id ?? b.find((x) => x.status !== "Active")?.id ?? b[0]?.id ?? "";
            });
        } catch (e) {
            toast((e as Error).message);
            setBots((x) => x ?? []);
            setHistory((x) => x ?? []);
        }
        apiJson<{ minutes_included: number; minutes_used: number; minutes_topup: number }>("/api/voice/overview")
            .then((o) => setMinutes(Math.max(o.minutes_included - o.minutes_used, 0) + o.minutes_topup))
            .catch(() => {});
    }, [toast]);

    useEffect(() => {
        if (!currentUserId()) {
            router.push("/auth/login");
            return;
        }
        load();
        apiJson<{ name: string; email: string }>("/api/auth/profile").then(setProfile).catch(() => {});
    }, [router, load]);

    const activeSub = useMemo(() => {
        const map: Record<string, Sub> = {};
        for (const s of subs) if (s.status === "active" && !map[s.bot_id]) map[s.bot_id] = s;
        return map;
    }, [subs]);

    const selectedBot = bots?.find((b) => b.id === botId);

    const buy = async (plan: (typeof PLANS)[number]) => {
        if (!selectedBot) return toast("Create an assistant first.");
        setPaying(plan.name);
        try {
            const order = await apiJson<{ order_id: string; amount: number; currency: string; key_id: string }>(
                "/api/payments/create-subscription-order", { method: "POST", json: { plan_name: plan.name, bot_id: selectedBot.id } });
            const result = await payAndVerify(order, { description: `${plan.label} for ${selectedBot.name}`, email: profile?.email, name: profile?.name });
            if (result) {
                toast(result.message);
                load();
            }
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setPaying(null);
        }
    };

    const toggleRenew = async (bot: Bot, enabled: boolean) => {
        try {
            await apiJson(`/api/payments/toggle-auto-renew?enabled=${enabled}&bot_id=${bot.id}`, { method: "POST" });
            setSubs((list) => list.map((s) => (s.bot_id === bot.id ? { ...s, auto_renewal: enabled } : s)));
            toast(enabled ? `${bot.name} will renew automatically` : `${bot.name} won't renew automatically`);
        } catch (e) {
            toast((e as Error).message);
        }
    };

    return (
        <div className="min-h-screen bg-paper text-ink">
            <AppHeader />
            <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 pb-24">
                <h1 className="text-2xl font-semibold tracking-tight">Billing</h1>
                <p className="text-sm text-stone-500 mt-1">Plans are per assistant. A plan keeps that assistant live on your website.</p>

                <section className="mt-8">
                    <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3 mb-4">
                        <div>
                            <h2 className="text-[15px] font-semibold">Choose a plan</h2>
                            <p className="text-[13px] text-stone-500 mt-0.5">Buying again extends the current plan; unused days carry over.</p>
                        </div>
                        <label className="flex items-center gap-2 text-[13px] text-stone-600">
                            For
                            {bots === null ? <Skeleton className="h-9 w-56" /> : (
                                <Select aria-label="Assistant" className="w-56" value={botId} onChange={(e) => setBotId(e.target.value)} disabled={!bots.length}>
                                    {!bots.length && <option>No assistants yet</option>}
                                    {bots.map((b) => <option key={b.id} value={b.id}>{b.name} ({b.id.slice(0, 6)})</option>)}
                                </Select>
                            )}
                        </label>
                    </div>

                    <div className="grid gap-4 md:grid-cols-3">
                        {PLANS.map((plan) => (
                            <Card key={plan.name} className={cn("p-5 flex flex-col", plan.popular && "border-plum ring-1 ring-plum")}>
                                <div className="flex items-baseline justify-between">
                                    <h3 className="text-sm font-semibold">{plan.label}</h3>
                                    {plan.popular && <span className="text-xs text-plum font-medium">Most popular</span>}
                                </div>
                                <p className="mt-3">
                                    <span className="text-3xl font-semibold tracking-tight tabular-nums">{inr(plan.price)}</span>
                                    <span className="ml-2 text-sm text-stone-400 line-through tabular-nums">{inr(plan.originalPrice)}</span>
                                </p>
                                <p className="text-xs text-stone-500 mt-1">{plan.perMonth}</p>
                                <p className="text-[13px] text-stone-600 mt-3">{plan.description}</p>
                                <ul className="mt-4 space-y-2 text-[13px] flex-1">
                                    {plan.features.map((f) => (
                                        <li key={f} className="flex gap-2"><Check size={14} className="mt-0.5 text-plum shrink-0" aria-hidden />{f}</li>
                                    ))}
                                </ul>
                                <Button variant={plan.popular ? "primary" : "secondary"} className="mt-5 w-full"
                                        disabled={!selectedBot || !!paying} onClick={() => buy(plan)}>
                                    {paying === plan.name ? "Opening payment…" : selectedBot?.status === "Active" ? `Extend by ${plan.label}` : `Choose ${plan.label}`}
                                </Button>
                            </Card>
                        ))}
                    </div>
                </section>

                <div className="grid gap-6 lg:grid-cols-3 mt-10">
                    <section className="lg:col-span-2">
                        <SectionHeader title="Your assistants" />
                        <Card>
                            {bots === null ? (
                                <div className="p-5 space-y-3"><Skeleton className="h-10" /><Skeleton className="h-10" /></div>
                            ) : !bots.length ? (
                                <EmptyState title="No assistants yet" body="Create an assistant, then pick a plan for it here." action={<Link href="/dashboard"><Button size="sm">Go to assistants</Button></Link>} />
                            ) : (
                                <ul>
                                    {bots.map((b) => {
                                        const sub = activeSub[b.id];
                                        return (
                                            <li key={b.id} className="grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] gap-x-4 gap-y-1 items-center px-5 py-3 border-t border-line first:border-t-0">
                                                <div className="min-w-0">
                                                    <p className="text-sm font-medium truncate">{b.name}</p>
                                                    <p className="text-xs text-stone-400 font-mono">{b.id.slice(0, 8)}</p>
                                                </div>
                                                <div className="text-[13px] row-start-2 sm:row-start-auto">
                                                    {b.status === "Active"
                                                        ? <><Status tone="good">{b.plan.replace(" Plan", "")}</Status><span className="text-xs text-stone-500 ml-2">until {b.expiry}</span></>
                                                        : <Status tone="neutral">No active plan</Status>}
                                                </div>
                                                <div className="row-span-2 sm:row-span-1 justify-self-end">
                                                    {sub ? (
                                                        <label className="flex items-center gap-2 text-xs text-stone-600">
                                                            Auto-renew
                                                            <Switch checked={sub.auto_renewal} onChange={(v) => toggleRenew(b, v)} label={`Auto-renew ${b.name}`} />
                                                        </label>
                                                    ) : (
                                                        <Button size="sm" onClick={() => { setBotId(b.id); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Choose plan</Button>
                                                    )}
                                                </div>
                                            </li>
                                        );
                                    })}
                                </ul>
                            )}
                        </Card>
                    </section>

                    <section>
                        <SectionHeader title="Voice minutes" />
                        <Card className="p-5">
                            <p className="tabular-nums">
                                <span className="text-[28px] leading-none font-semibold tracking-tight">{minutes === null ? "–" : formatNumber(minutes)}</span>
                                <span className="text-sm text-stone-500"> min left</span>
                            </p>
                            <p className="text-[13px] text-stone-500 mt-2">Used by phone calls and test calls. Top-up minutes don&apos;t expire.</p>
                            <Link href="/dashboard/voice" className="inline-flex items-center gap-1 mt-4 text-[13px] text-plum hover:underline underline-offset-4">
                                Buy minutes <ArrowRight size={13} />
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
                            <EmptyState title="No payments yet" body="Receipts for plans and minute packs show up here." />
                        ) : (
                            <table className="w-full text-sm">
                                <thead className="hidden sm:table-header-group">
                                    <tr className="text-left text-[13px] text-stone-500">
                                        <th className="font-normal px-5 py-3">Date</th>
                                        <th className="font-normal px-3 py-3">Item</th>
                                        <th className="font-normal px-3 py-3">Assistant</th>
                                        <th className="font-normal px-3 py-3 text-right">Amount</th>
                                        <th className="font-normal px-5 py-3 text-right">Payment ID</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {history.map((p) => (
                                        <tr key={p.transaction_id} className="border-t border-line first:border-t-0 sm:first:border-t">
                                            <td className="px-5 py-3 text-stone-600 whitespace-nowrap">{p.date}</td>
                                            <td className="px-3 py-3">{p.plan_name}</td>
                                            <td className="hidden sm:table-cell px-3 py-3 text-stone-600">{bots?.find((b) => b.id === p.bot_id)?.name ?? "–"}</td>
                                            <td className="px-3 py-3 text-right tabular-nums">{inr(p.amount)}</td>
                                            <td className="hidden sm:table-cell px-5 py-3 text-right text-xs text-stone-400 font-mono">{p.transaction_id}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </Card>
                </section>
            </main>
        </div>
    );
}
