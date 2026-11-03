"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Card, EmptyState, Notice, Skeleton, Status, cn } from "@/components/ui";
import { STATUS, type IgOverview } from "@/lib/instagram";
import { useApi } from "@/lib/useApi";
import { formatNumber, formatWhen } from "@/lib/voice/api";

export default function InstagramOverviewPage() {
    const overview = useApi<IgOverview>("/api/instagram");

    if (overview.loading) {
        return <div className="space-y-6"><Skeleton className="h-[116px]" /><Skeleton className="h-64" /></div>;
    }
    if (overview.error || !overview.data) {
        return <p className="text-sm text-signal">Couldn&apos;t load Instagram. {overview.error}</p>;
    }
    const o = overview.data;
    const broken = o.accounts.find((a) => a.status === "token" || a.status === "permission");

    return (
        <>
            {broken && (
                <Notice title={`@${broken.username ?? "Your account"} needs attention`}
                        action={<Link href="/dashboard/instagram/settings" className="text-[13px] font-medium text-plum hover:underline">Open settings</Link>}>
                    {broken.status_detail ?? "Instagram isn't accepting Nimmi's sign-in."} Until it&apos;s fixed, the assistant can&apos;t answer.
                </Notice>
            )}

            <Card className="grid grid-cols-1 sm:grid-cols-3 [&>*]:border-line">
                <Metric label="Chats this month" value={formatNumber(o.month.chats)} />
                <Metric label="Answered by the assistant" value={formatNumber(o.month.answered)} className="border-t sm:border-t-0 sm:border-l" />
                <Link href="/dashboard/instagram/inbox?view=person" className="border-t sm:border-t-0 sm:border-l hover:bg-stone-50 transition-colors">
                    <Metric label="Waiting for your team" value={formatNumber(o.month.waiting)} note="Asked for a person, or a teammate has it" />
                </Link>
            </Card>

            <div className="grid gap-6 lg:grid-cols-3 mt-6">
                <Card className="lg:col-span-2">
                    <div className="flex items-center justify-between px-5 pt-5">
                        <h2 className="text-[15px] font-semibold">Your account</h2>
                        <Link href="/dashboard/instagram/settings" className="text-[13px] text-plum hover:underline inline-flex items-center gap-1">Manage <ArrowRight size={13} /></Link>
                    </div>
                    {o.accounts.length === 0 ? (
                        <EmptyState title="No Instagram account yet"
                                    body={o.available ? "Connect your Instagram professional account in Settings. It takes a minute: you sign in to Instagram and allow messages."
                                        : "This comes once Nimmi's Instagram app is approved by Meta. Until then, everything else works as usual."}
                                    action={o.available ? <Link href="/dashboard/instagram/settings" className="text-sm font-medium text-plum hover:underline">Connect Instagram</Link> : undefined} />
                    ) : (
                        <ul className="mt-3">
                            {o.accounts.map((a) => (
                                <li key={a.id} className="flex flex-wrap items-center gap-3 px-5 py-3 border-t border-line">
                                    <span className="min-w-0 flex-1">
                                        <span className="block text-sm font-medium truncate">@{a.username ?? a.ig_id}</span>
                                        <span className="block text-[13px] text-stone-500">
                                            {[a.bot_name ? `Answered by ${a.bot_name}` : "No assistant chosen", a.ai_enabled ? null : "assistant off",
                                                a.last_inbound_at ? `last message ${formatWhen(a.last_inbound_at).toLowerCase()}` : null].filter(Boolean).join(" · ")}
                                        </span>
                                    </span>
                                    <Status tone={STATUS[a.status]?.tone ?? "neutral"}>{STATUS[a.status]?.text ?? a.status}</Status>
                                </li>
                            ))}
                        </ul>
                    )}
                </Card>
                <Card className="p-5">
                    <h2 className="text-[15px] font-semibold">How it works</h2>
                    <ul className="mt-3 space-y-2.5 text-[13px] text-stone-600">
                        <li>The assistant answers within seconds, in their language, inside Instagram&apos;s 24 hours after their last message.</li>
                        <li>After 24 hours only your team can reply, up to 7 days, from the Inbox or Live chat.</li>
                        <li>Everyone who writes is a lead in Leads, with their Instagram name. A number or email they type joins them to the lead that has it.</li>
                        <li>Reply from the Instagram app and the assistant steps back from that chat for a while.</li>
                    </ul>
                </Card>
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
