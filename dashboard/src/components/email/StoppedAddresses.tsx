"use client";

import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { Button, Card, EmptyState, Input, Segmented, Skeleton, useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import type { StopReason, Suppressions } from "@/lib/email";
import { formatWhen } from "@/lib/voice/api";

const PAGE = 50;
type Filter = "" | StopReason;

/** Addresses the workspace doesn't email, and why (backend mail/suppress.py). */
export function StoppedAddresses() {
    const toast = useToast();
    const [reason, setReason] = useState<Filter>("");
    const [query, setQuery] = useState("");
    const [q, setQ] = useState("");
    const [data, setData] = useState<Suppressions | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState<string | null>(null);

    useEffect(() => { const t = setTimeout(() => setQ(query), 300); return () => clearTimeout(t); }, [query]);
    const path = (offset: number) => `/api/email/suppressions?${new URLSearchParams({ reason, q, offset: String(offset), limit: String(PAGE) })}`;
    useEffect(() => {
        setData(null);
        setError(null);
        apiJson<Suppressions>(path(0)).then(setData).catch((e) => setError((e as Error).message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [reason, q]);

    const more = async () => {
        if (!data) return;
        try {
            const next = await apiJson<Suppressions>(path(data.items.length));
            setData({ ...next, items: [...data.items, ...next.items] });
        } catch (e) {
            toast((e as Error).message);
        }
    };

    const emailAgain = async (id: string, address: string) => {
        setBusy(id);
        try {
            await apiJson(`/api/email/suppressions/${id}`, { method: "DELETE" });
            setData(data && { ...data, items: data.items.filter((r) => r.id !== id), total: data.total - 1 });
            toast(`${address} can get your emails again`);
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(null);
        }
    };

    const c = data?.counts ?? {};
    const all = Object.values(c).reduce((a, b) => a + (b ?? 0), 0);
    const label = (r: Filter, text: string) => (data ? `${text} ${(r ? c[r] ?? 0 : all).toLocaleString("en-IN")}` : text);

    return (
        <Card>
            <div id="stopped" className="px-5 pt-4 pb-3 scroll-mt-6">
                <h2 className="text-sm font-medium">Addresses you don&apos;t email</h2>
                <p className="text-[13px] text-stone-500 mt-0.5 max-w-2xl">
                    People who unsubscribed or reported an email as spam, addresses that bounced (they don&apos;t exist), and people your team stopped.
                    Nimmi skips them in every automatic and bulk email.
                </p>
            </div>
            <div className="flex flex-wrap items-center gap-3 px-5 pb-3">
                <div className="overflow-x-auto max-w-full [&_button]:whitespace-nowrap">
                    <Segmented label="Filter by reason" value={reason} onChange={setReason} options={[
                        { value: "", label: label("", "All") }, { value: "unsubscribed", label: label("unsubscribed", "Unsubscribed") },
                        { value: "complaint", label: label("complaint", "Spam reports") }, { value: "bounce", label: label("bounce", "Bounced") },
                        { value: "team", label: label("team", "Stopped by you") },
                    ]} />
                </div>
                <div className="relative flex-1 min-w-48">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" aria-hidden />
                    <Input aria-label="Search addresses" placeholder="Search an address" className="pl-8" value={query} onChange={(e) => setQuery(e.target.value)} />
                </div>
            </div>
            {error ? <p className="px-5 pb-4 text-sm text-signal">{error}</p> : !data ? (
                <div className="px-5 pb-5 space-y-2"><Skeleton className="h-9" /><Skeleton className="h-9" /></div>
            ) : data.items.length === 0 ? (
                <EmptyState title={reason || q ? "No addresses match" : "Nobody is stopped"} body={reason || q ? "Try another filter or search." : "When someone unsubscribes or an address bounces, it shows here."} />
            ) : (
                <>
                    <ul>
                        {data.items.map((r) => (
                            <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3 border-t border-line text-[13px]">
                                <span className="min-w-0 flex-1 truncate">{r.email}</span>
                                <span className="text-stone-600">{r.text}{r.bot_name ? ` (${r.bot_name})` : ""}</span>
                                <span className="text-xs text-stone-500 tabular-nums">{r.created_at ? formatWhen(r.created_at) : ""}</span>
                                {r.removable && (
                                    <Button size="sm" variant="ghost" onClick={() => emailAgain(r.id, r.email)} disabled={busy === r.id}>Email again</Button>
                                )}
                            </li>
                        ))}
                    </ul>
                    {data.items.length < data.total && (
                        <div className="px-5 py-3 border-t border-line text-center">
                            <Button size="sm" variant="ghost" onClick={more}>Show more ({(data.total - data.items.length).toLocaleString("en-IN")} left)</Button>
                        </div>
                    )}
                </>
            )}
        </Card>
    );
}
