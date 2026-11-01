"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { Button, Card, EmptyState, Notice, Skeleton, Status, useToast } from "@/components/ui";
import { AgentDrafts } from "@/components/email/AgentDrafts";
import { DraftReview } from "@/components/email/DraftReview";
import { apiJson } from "@/lib/api";
import { DRAFTS_CHANGED, type Draft, type Drafts } from "@/lib/email";
import { useApi } from "@/lib/useApi";
import { formatWhen } from "@/lib/voice/api";

function tone(d: Draft): { tone: "warn" | "neutral" | "good"; text: string } {
    if (d.state === "writing") return { tone: "neutral", text: "Being written" };
    if (d.note) return { tone: "warn", text: "Needs a look" };
    return { tone: "good", text: "Ready" };
}

function DraftsPage() {
    const toast = useToast();
    const router = useRouter();
    const params = useSearchParams();
    const list = useApi<Drafts>("/api/email/drafts");
    const [busy, setBusy] = useState(false);
    const open = params.get("draft");
    const { reload } = list;

    // Emails being written come in by themselves.
    const writing = !!list.data?.items.some((d) => d.state === "writing");
    useEffect(() => {
        if (!writing) return;
        const t = setInterval(() => { void reload(); }, 4000);
        return () => clearInterval(t);
    }, [writing, reload]);

    const show = (id: string | null) => router.replace(id ? `/dashboard/email/drafts?draft=${id}` : "/dashboard/email/drafts", { scroll: false });
    const answer = async (botId: string, accept: boolean) => {
        setBusy(true);
        try {
            await apiJson("/api/email/drafts/suggestion", { method: "POST", json: { bot_id: botId, accept } });
            if (accept) toast("Emails after calls now go automatically");
            await reload();
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    if (list.error) return <p className="text-sm text-signal">{list.error}</p>;
    if (!list.data) return <Skeleton className="h-64" />;
    const { items, total, suggest } = list.data;
    return (
        <div className="space-y-5">
            <AgentDrafts />
            {suggest.map((s) => (
                <Notice key={s.bot_id} title={`${s.bot_name}'s emails could go automatically`}
                        action={<div className="flex gap-2">
                            <Button size="sm" variant="ghost" disabled={busy} onClick={() => answer(s.bot_id, false)}>Not now</Button>
                            <Button size="sm" variant="primary" disabled={busy} onClick={() => answer(s.bot_id, true)}>Send automatically</Button>
                        </div>}>
                    You approved {s.approved} of its emails, {s.unchanged} of them without changing anything. They&apos;d go by themselves, and
                    the ones the AI&apos;s check isn&apos;t sure of, or from unhappy callers, would still wait here.
                </Notice>
            ))}
            {items.length === 0 && list.data.agent ? null : items.length === 0 ? (
                <Card>
                    <EmptyState title="No emails waiting" body={<>
                        When an assistant&apos;s email after a call is set to Review first, each one waits here for your OK.
                        Set it in <Link href="/dashboard/email/automations" className="text-plum hover:underline">Automations</Link>.
                    </>} />
                </Card>
            ) : (
                <Card>
                    <div className="px-5 pt-4 pb-3 border-b border-line">
                        <h3 className="text-sm font-medium">{total === 1 ? "1 email waiting" : `${total} emails waiting`}</h3>
                        <p className="text-[13px] text-stone-500 mt-0.5">The AI wrote these after calls. Nothing goes until you approve it.</p>
                    </div>
                    <ul>
                        {items.map((d) => {
                            const s = tone(d);
                            return (
                                <li key={d.id} className="border-t border-line first:border-t-0">
                                    <button type="button" onClick={() => show(d.id)} className="w-full flex items-center gap-4 px-5 py-3.5 text-left hover:bg-paper/70 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-plum">
                                        <span className="min-w-0 flex-1">
                                            <span className="block text-sm truncate">{d.name || d.to}</span>
                                            <span className="block text-[13px] text-stone-500 truncate">
                                                {d.name ? `${d.to} · ` : ""}{d.direction === "inbound" ? "Incoming call" : "Outgoing call"}
                                                {d.created_at ? ` · ${formatWhen(d.created_at)}` : ""}{d.bot_name ? ` · ${d.bot_name}` : ""}
                                            </span>
                                            {(d.note || d.recap[0]) && <span className="block text-[13px] text-stone-600 truncate mt-0.5">{d.note || d.recap[0]}</span>}
                                        </span>
                                        <Status tone={s.tone}>{s.text}</Status>
                                        <ChevronRight size={15} className="text-stone-400 shrink-0" aria-hidden />
                                    </button>
                                </li>
                            );
                        })}
                    </ul>
                </Card>
            )}
            {open && (
                <DraftReview id={open} onClose={() => { show(null); void reload(); }}
                             onDone={() => { show(null); void reload(); window.dispatchEvent(new Event(DRAFTS_CHANGED)); }} />
            )}
        </div>
    );
}

export default function Page() {
    return <Suspense fallback={<Skeleton className="h-64" />}><DraftsPage /></Suspense>;
}
