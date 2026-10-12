"use client";

import { useState } from "react";
import { Button, Card, Dialog, Skeleton, cn, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { payAndVerify } from "@/lib/razorpay";
import { useApi } from "@/lib/useApi";
import { formatDate, formatINR } from "@/lib/voice/api";

/** Prepaid Nimmi balance; mirrors GET /api/billing/balance. Pays for phone numbers. */
export interface BalanceInfo {
    balance: number;            // INR
    monthly_commitment: number; // INR a month for the workspace's self-serve numbers
    topups: number[];           // amounts that can be added, INR
    entries: { id: string; amount: number; kind: "topup" | "number_rental" | "refund" | "adjustment"; note: string; created_at: string | null }[];
}

export const useBalance = () => useApi<BalanceInfo>("/api/billing/balance");

const KIND_LABEL: Record<BalanceInfo["entries"][number]["kind"], string> = {
    topup: "Added", number_rental: "Number rent", refund: "Refund", adjustment: "Adjustment",
};

/** Pick an amount, pay with Razorpay, credit the balance. `needed` preselects the smallest amount that covers it. */
export function TopUpDialog({ open, onClose, amounts, needed = 0, onPaid }: {
    open: boolean; onClose: () => void; amounts: number[]; needed?: number; onPaid: () => void;
}) {
    const toast = useToast();
    const fallback = amounts.find((a) => a >= needed) ?? amounts[amounts.length - 1];
    const [picked, setPicked] = useState<number | null>(null);
    const [busy, setBusy] = useState(false);
    const amount = picked ?? fallback;

    const pay = async () => {
        setBusy(true);
        try {
            const order = await apiJson<{ order_id: string; amount: number; currency: string; key_id: string }>(
                "/api/payments/create-balance-order", { method: "POST", json: { amount } });
            const result = await payAndVerify(order, { description: `Add ${formatINR(amount)} to your Nimmi balance` });
            if (result) {
                toast(result.message);
                onPaid();
                onClose();
            }
        } catch (e) {
            toast((e as Error).message || "Payment didn't go through");
        } finally {
            setBusy(false);
        }
    };

    return (
        <Dialog
            open={open}
            onClose={() => { setPicked(null); onClose(); }}
            title="Add money to your balance"
            description="Your balance pays for phone numbers each month. It doesn't expire."
            footer={<>
                <Button variant="ghost" onClick={onClose}>Cancel</Button>
                <Button variant="primary" onClick={pay} disabled={busy}>{busy ? "Opening payment…" : `Pay ${formatINR(amount)}`}</Button>
            </>}
        >
            <div role="radiogroup" aria-label="Amount" className="grid grid-cols-2 gap-2">
                {amounts.map((a) => (
                    <button
                        key={a}
                        type="button"
                        role="radio"
                        aria-checked={amount === a}
                        onClick={() => setPicked(a)}
                        className={cn(
                            "h-12 rounded-md border text-sm tabular-nums transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum",
                            amount === a ? "border-plum bg-plum-tint text-plum font-medium" : "border-line-strong hover:bg-stone-50",
                        )}
                    >
                        {formatINR(a)}
                    </button>
                ))}
            </div>
            {needed > 0 && <p className="text-[13px] text-stone-500 mt-3">You need at least {formatINR(needed)} more for this number.</p>}
        </Dialog>
    );
}

/** Balance figure, what numbers cost each month, an Add money action and (optionally) recent activity. */
export function BalanceCard({ info, showActivity = false, onPaid }: {
    info: ReturnType<typeof useBalance>; showActivity?: boolean; onPaid?: () => void;
}) {
    const [topUp, setTopUp] = useState(false);

    if (info.loading && !info.data) return <Skeleton className="h-36" />;
    if (!info.data) return null; // members without billing access
    const { balance, monthly_commitment, topups, entries } = info.data;
    const short = monthly_commitment > balance;

    return (
        <Card>
            <div className="flex flex-wrap items-end justify-between gap-4 p-5">
                <div>
                    <p className="tabular-nums">
                        <span className="text-[28px] leading-none font-semibold tracking-tight">{formatINR(balance)}</span>
                    </p>
                    <p className={cn("text-[13px] mt-2", short ? "text-signal" : "text-stone-500")}>
                        {monthly_commitment
                            ? short
                                ? `Your numbers need ${formatINR(monthly_commitment)} a month. Add money so they keep answering.`
                                : `Your numbers use ${formatINR(monthly_commitment)} a month from this.`
                            : "Pays for phone numbers. Nothing is charged until you get one."}
                    </p>
                </div>
                <Button size="sm" variant={short ? "primary" : "secondary"} onClick={() => setTopUp(true)}>Add money</Button>
            </div>

            {showActivity && entries.length > 0 && (
                <ul className="border-t border-line">
                    {entries.slice(0, 8).map((e) => (
                        <li key={e.id} className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 px-5 py-2.5 border-t border-line first:border-t-0 text-[13px]">
                            <div className="min-w-0">
                                <p className="truncate">{e.note || KIND_LABEL[e.kind]}</p>
                                <p className="text-xs text-stone-500">{KIND_LABEL[e.kind]}{e.created_at ? ` · ${formatDate(e.created_at)}` : ""}</p>
                            </div>
                            <p className={cn("tabular-nums self-center", e.amount > 0 ? "text-emerald-700" : "text-stone-700")}>
                                {e.amount > 0 ? "+" : "−"}{formatINR(Math.abs(e.amount))}
                            </p>
                        </li>
                    ))}
                </ul>
            )}

            <TopUpDialog open={topUp} onClose={() => setTopUp(false)} amounts={topups} needed={Math.max(0, monthly_commitment - balance)} onPaid={() => { info.reload(); onPaid?.(); }} />
        </Card>
    );
}
