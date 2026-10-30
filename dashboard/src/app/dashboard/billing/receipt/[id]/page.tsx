"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Printer } from "lucide-react";
import { Button, Skeleton } from "@/components/ui";
import { apiJson } from "@/lib/api";
import { inr } from "@/lib/plans";

/** A payment's receipt (backend payments.py `receipt`), to print or save as PDF. Not a tax invoice: no GST is charged. */
type Receipt = {
    number: string; date: string; item: string; assistant: string | null; amount: number; currency: string; payment_id: string;
    billed_to: { name: string; email: string }; seller: { name: string; website: string; email: string };
};

const when = (iso: string) => new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);

export default function ReceiptPage() {
    const { id } = useParams<{ id: string }>();
    const [receipt, setReceipt] = useState<Receipt | null>(null);
    const [error, setError] = useState<string | null>(null);
    useEffect(() => {
        apiJson<Receipt>(`/api/payments/receipt/${encodeURIComponent(id)}`).then(setReceipt).catch((e) => setError((e as Error).message));
    }, [id]);

    return (
        <div className="min-h-screen bg-paper text-ink print:bg-white">
            <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8 print:p-0">
                <div className="flex items-center justify-between gap-3 mb-5 print:hidden">
                    <Link href="/dashboard/billing" className="inline-flex items-center gap-1.5 text-[13px] text-stone-600 hover:text-ink">
                        <ArrowLeft size={14} aria-hidden /> Billing
                    </Link>
                    <Button size="sm" onClick={() => window.print()} disabled={!receipt}><Printer size={14} aria-hidden /> Print or save as PDF</Button>
                </div>
                {error ? (
                    <p className="text-sm text-signal">{error}</p>
                ) : !receipt ? (
                    <Skeleton className="h-96" />
                ) : (
                    <article className="bg-white border border-line rounded-lg p-8 print:border-0 print:p-0">
                        <header className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                            <div>
                                <p className="text-lg font-semibold">{receipt.seller.name}</p>
                                <p className="text-[13px] text-stone-500">{receipt.seller.website}</p>
                                <p className="text-[13px] text-stone-500">{receipt.seller.email}</p>
                            </div>
                            <div className="sm:text-right">
                                <h1 className="text-xl font-semibold tracking-tight">Receipt</h1>
                                <p className="text-[13px] text-stone-500 tabular-nums">{receipt.number}</p>
                                <p className="text-[13px] text-stone-500">
                                    {when(receipt.date).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}
                                </p>
                            </div>
                        </header>

                        <section className="mt-8">
                            <p className="text-[12px] uppercase tracking-wide text-stone-500">Billed to</p>
                            {receipt.billed_to.name && <p className="text-sm mt-1">{receipt.billed_to.name}</p>}
                            <p className="text-sm text-stone-600">{receipt.billed_to.email}</p>
                        </section>

                        <table className="w-full text-sm mt-8">
                            <thead>
                                <tr className="text-left text-[12px] uppercase tracking-wide text-stone-500 border-b border-line">
                                    <th className="font-normal py-2">Item</th>
                                    <th className="font-normal py-2 text-right">Amount</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr className="border-b border-line">
                                    <td className="py-3">
                                        {receipt.item}
                                        {receipt.assistant && <span className="block text-[13px] text-stone-500">For {receipt.assistant}</span>}
                                    </td>
                                    <td className="py-3 text-right tabular-nums">{inr(receipt.amount)}</td>
                                </tr>
                            </tbody>
                            <tfoot>
                                <tr>
                                    <td className="pt-4 font-semibold">Paid</td>
                                    <td className="pt-4 text-right font-semibold tabular-nums">{inr(receipt.amount)}</td>
                                </tr>
                            </tfoot>
                        </table>

                        <p className="text-[13px] text-stone-500 mt-8">
                            Paid through Razorpay. Payment ID <span className="font-mono">{receipt.payment_id}</span>.
                        </p>
                        <p className="text-[12px] text-stone-400 mt-2">This is a payment receipt, not a tax invoice. No GST was charged.</p>
                    </article>
                )}
            </div>
        </div>
    );
}
