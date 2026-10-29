"use client";

import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";
import { Card, EmptyState, Notice, Skeleton, Status, cn } from "@/components/ui";
import { useApi } from "@/lib/useApi";
import { formatNumber, formatWhen } from "@/lib/voice/api";
import { REPLY_RATE_INR, type WaNumber, type WaOverview } from "@/lib/whatsapp";

const QUALITY: Record<string, { tone: "good" | "warn" | "bad" | "neutral"; label: string }> = {
    GREEN: { tone: "good", label: "High quality" },
    YELLOW: { tone: "warn", label: "Medium quality" },
    RED: { tone: "bad", label: "Low quality" },
};

export default function WhatsAppOverviewPage() {
    const overview = useApi<WaOverview>("/api/whatsapp/overview");

    if (overview.loading) {
        return (
            <div className="space-y-6">
                <Skeleton className="h-[116px]" />
                <div className="grid gap-6 lg:grid-cols-3"><Skeleton className="h-64 lg:col-span-2" /><Skeleton className="h-64" /></div>
            </div>
        );
    }
    if (overview.error || !overview.data) {
        return <p className="text-sm text-signal">Couldn&apos;t load WhatsApp. {overview.error}</p>;
    }
    const o = overview.data;
    const broken = o.numbers.find((n) => n.status === "error");

    return (
        <>
            {broken && (
                <Notice title={`${broken.display_number ?? "Your number"} needs attention`}
                        action={<Link href="/dashboard/whatsapp/settings" className="text-[13px] font-medium text-plum hover:underline">Open settings</Link>}>
                    {broken.status_detail ?? "Meta isn't accepting its access token."} Until it&apos;s fixed, nothing can be sent from this number.
                </Notice>
            )}

            <Card className="grid grid-cols-2 lg:grid-cols-4 [&>*]:border-line">
                <Metric label="Chats this month" value={formatNumber(o.month.chats)} />
                <Metric label="Messages from customers" value={formatNumber(o.month.from_customers)} className="border-l" />
                <Metric label="Answered by the assistant" value={formatNumber(o.month.by_ai)} note={o.month.by_team ? `${formatNumber(o.month.by_team)} by your team` : undefined}
                        className="border-t lg:border-t-0 lg:border-l" />
                <Link href="/dashboard/whatsapp/inbox?view=person" className="border-t border-l lg:border-t-0 hover:bg-stone-50 transition-colors">
                    <Metric label="Waiting for your team" value={formatNumber(o.month.waiting_for_team)} note="Asked for a person, or a teammate has it" />
                </Link>
            </Card>

            <div className="grid gap-6 lg:grid-cols-3 mt-6">
                <Card className="lg:col-span-2">
                    <div className="flex items-center justify-between px-5 pt-5">
                        <h2 className="text-[15px] font-semibold">Your numbers</h2>
                        <Link href="/dashboard/whatsapp/settings" className="text-[13px] text-plum hover:underline inline-flex items-center gap-1">
                            Manage <ArrowRight size={13} />
                        </Link>
                    </div>
                    {o.numbers.length === 0 ? (
                        <EmptyState title="No WhatsApp number connected yet"
                                    body="Connect your WhatsApp Business number and your assistant starts answering customers there."
                                    action={<Link href="/dashboard/whatsapp/settings" className="inline-flex items-center h-9 px-4 rounded-md bg-plum text-white text-sm font-medium hover:bg-plum-hover">Connect a number</Link>} />
                    ) : (
                        <ul className="mt-3">
                            {o.numbers.map((n) => <NumberRow key={n.id} n={n} free={o.setup.free_replies} />)}
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

function NumberRow({ n, free }: { n: WaNumber; free: number }) {
    const used = n.replies_this_month ?? 0;
    const pct = Math.min((used / free) * 100, 100);
    const quality = QUALITY[n.quality_rating ?? ""];
    return (
        <li className="px-5 py-4 border-t border-line">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <span className="text-sm font-medium tabular-nums">{n.display_number ?? n.phone_number_id}</span>
                {n.verified_name && <span className="text-[13px] text-stone-500">{n.verified_name}</span>}
                <span className="ml-auto flex items-center gap-4">
                    {quality && <Status tone={quality.tone}>{quality.label}</Status>}
                    <Status tone={n.status === "connected" ? (n.ai_enabled ? "good" : "neutral") : "bad"}>
                        {n.status !== "connected" ? "Needs attention" : n.ai_enabled ? "Assistant answering" : "Assistant off"}
                    </Status>
                </span>
            </div>
            <p className="text-[13px] text-stone-500 mt-1">
                {n.bot_name ? `Answered by ${n.bot_name}` : "Answered by your first active assistant"}
                {n.last_inbound_at ? ` · last message ${formatWhen(n.last_inbound_at)}` : " · no messages yet"}
            </p>
            <div className="mt-3">
                <div className="flex justify-between text-xs text-stone-500 tabular-nums">
                    <span>Free replies this month</span>
                    <span>{formatNumber(used)} of {formatNumber(free)} used</span>
                </div>
                <div className="mt-1.5 h-1.5 rounded-full bg-stone-100 overflow-hidden" role="progressbar" aria-label="Free replies used"
                     aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
                    <div className={cn("h-full rounded-full", pct >= 90 ? "bg-amber-500" : "bg-plum")} style={{ width: `${pct}%` }} />
                </div>
                <p className="text-xs text-stone-500 mt-1.5">
                    Replies within 24 hours of a customer&apos;s message are free up to {formatNumber(free)} a month per number. After that, Meta
                    charges about ₹{REPLY_RATE_INR} per reply in India and bills you directly.
                </p>
            </div>
        </li>
    );
}

function SetupCard({ setup }: { setup: WaOverview["setup"] }) {
    const steps = [
        { done: setup.connected, title: "Connect your WhatsApp number", body: "Link your WhatsApp Business number to Nimmi.", href: "/dashboard/whatsapp/settings" },
        { done: setup.connected && setup.app_secret, title: "Add your app secret", body: "Lets Nimmi check that messages really come from Meta.", href: "/dashboard/whatsapp/settings" },
        { done: setup.answering, title: "Let the assistant answer", body: "Choose the assistant and how it should behave.", href: "/dashboard/whatsapp/assistant" },
        { done: setup.files > 0, title: "Add files to send", body: "Brochures, price lists or photos the assistant can share.", href: "/dashboard/whatsapp/files" },
        { done: setup.first_message, title: "Get your first message", body: "Message your number from your phone to see it work.", href: "/dashboard/whatsapp/inbox" },
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
                            <span className={cn("mt-0.5 h-5 w-5 shrink-0 rounded-full flex items-center justify-center text-[11px] tabular-nums",
                                s.done ? "bg-plum-tint text-plum" : "border border-line-strong text-stone-500")}>
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
