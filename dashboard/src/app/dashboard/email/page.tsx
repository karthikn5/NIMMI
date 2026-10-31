"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Card, Notice, Skeleton, Status } from "@/components/ui";
import type { EmailOverview } from "@/lib/email";
import { useApi } from "@/lib/useApi";
import { formatWhen } from "@/lib/voice/api";

const n = (v: number) => v.toLocaleString("en-IN");

export default function EmailOverviewPage() {
    const o = useApi<EmailOverview>("/api/email/overview");
    if (o.error) return <p className="text-sm text-signal">{o.error}</p>;
    if (!o.data) return <div className="space-y-4"><Skeleton className="h-28" /><Skeleton className="h-64" /></div>;
    const d = o.data;
    const s = d.last_30_days;
    const on = d.automations.filter((a) => a.enabled);
    // Delivered, bounced and spam reports come from Resend's reports; without them only "sent" is known.
    const tiles: { label: string; value: number; hint?: string; tone?: "bad" }[] = [
        { label: "Sent", value: s.sent },
        ...(d.server.events ? [
            { label: "Delivered", value: s.delivered },
            { label: "Bounced", value: s.bounced, hint: "Addresses that don't exist", tone: s.bounced ? "bad" as const : undefined },
            { label: "Spam reports", value: s.complained, tone: s.complained ? "bad" as const : undefined },
        ] : []),
        { label: "Failed", value: s.failed, tone: s.failed ? "bad" as const : undefined },
        { label: "Scheduled", value: s.queued, hint: "Waiting for their time" },
    ];

    return (
        <div className="space-y-6">
            {!d.server.email && (
                <Notice title="Email sending isn't switched on yet">
                    Everything here is saved and shows in History, but nothing is delivered until Nimmi&apos;s email service is set up.
                </Notice>
            )}

            <section aria-labelledby="last-30">
                <h2 id="last-30" className="text-sm font-medium mb-3">Last 30 days</h2>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                    {tiles.map((t) => (
                        <Card key={t.label} className="p-4">
                            <p className="text-xs text-stone-500">{t.label}</p>
                            <p className={`text-2xl font-semibold tabular-nums mt-1 ${t.tone === "bad" ? "text-signal" : ""}`}>{n(t.value)}</p>
                            {t.hint && <p className="text-[11px] text-stone-400 mt-0.5">{t.hint}</p>}
                        </Card>
                    ))}
                </div>
                {d.complaint_rate !== null && d.complaint_rate > 0.001 && (
                    <p className="text-[13px] text-stone-600 mt-3">
                        {(d.complaint_rate * 100).toFixed(2)}% of your recent bulk emails were reported as spam. Gmail&apos;s limit is 0.3%; above it,
                        bulk email pauses. Send only to people who asked to hear from you.
                    </p>
                )}
            </section>

            <div className="grid lg:grid-cols-2 gap-6 items-start">
                <Card>
                    <div className="flex items-center justify-between gap-3 px-5 pt-4 pb-2">
                        <h2 className="text-sm font-medium">Automatic emails</h2>
                        <Link href="/dashboard/email/automations" className="text-[13px] text-plum hover:underline">Change</Link>
                    </div>
                    <ul>
                        {d.automations.map((a) => (
                            <li key={a.key} className="flex items-center justify-between gap-3 px-5 py-2.5 border-t border-line text-[13px]">
                                <span>{a.label}</span>
                                <Status tone={a.enabled ? "good" : "neutral"}>{a.enabled ? (a.emails > 1 ? `On, ${a.emails} emails` : "On") : "Off"}</Status>
                            </li>
                        ))}
                    </ul>
                    {on.length === 0 && (
                        <p className="px-5 py-3 border-t border-line text-[13px] text-stone-500">
                            None is on yet. Turn on the email after a chat or a call so people hear from you within minutes.
                        </p>
                    )}
                </Card>

                <Card>
                    <div className="flex items-center justify-between gap-3 px-5 pt-4 pb-2">
                        <h2 className="text-sm font-medium">Sending from</h2>
                        <Link href="/dashboard/email/settings" className="text-[13px] text-plum hover:underline">Settings</Link>
                    </div>
                    {d.domains.length === 0 ? (
                        <div className="px-5 pb-4 text-[13px] text-stone-600">
                            <p>Emails go from <span className="font-medium text-ink">{d.server.sending_address}</span> under your business&apos;s name, and replies come to you.</p>
                            <Link href="/dashboard/email/settings" className="inline-flex items-center gap-1 mt-2 text-plum hover:underline">
                                Send from your own domain <ArrowRight size={13} />
                            </Link>
                        </div>
                    ) : (
                        <ul>
                            {d.domains.map((dm) => (
                                <li key={dm.id} className="flex items-center justify-between gap-3 px-5 py-2.5 border-t border-line text-[13px]">
                                    <span className="truncate">{dm.name}</span>
                                    <Status tone={dm.status === "verified" ? "good" : dm.status === "failed" || dm.status === "temporary_failure" ? "bad" : "warn"}>
                                        {dm.status_label}
                                    </Status>
                                </li>
                            ))}
                        </ul>
                    )}
                    <div className="px-5 py-3 border-t border-line text-[13px] text-stone-600 flex items-center justify-between gap-3">
                        <span>{n(d.stopped)} {d.stopped === 1 ? "address isn't" : "addresses aren't"} emailed (unsubscribed, spam reports, bounces)</span>
                        <Link href="/dashboard/email/settings#stopped" className="text-plum hover:underline shrink-0">See</Link>
                    </div>
                </Card>
            </div>

            {d.problems.length > 0 && (
                <Card>
                    <div className="flex items-center justify-between gap-3 px-5 pt-4 pb-2">
                        <h2 className="text-sm font-medium">Recent problems</h2>
                        <Link href="/dashboard/email/history" className="text-[13px] text-plum hover:underline">History</Link>
                    </div>
                    <ul>
                        {d.problems.map((p) => (
                            <li key={p.id} className="px-5 py-3 border-t border-line text-[13px]">
                                <div className="flex items-center justify-between gap-3">
                                    <span className="truncate">{p.to}</span>
                                    <span className="text-xs text-stone-500 shrink-0">{p.created_at ? formatWhen(p.created_at) : ""}</span>
                                </div>
                                <p className="text-stone-500 mt-0.5 truncate">
                                    {p.complained_at ? "Reported as spam" : p.bounced_at ? `Bounced${p.event_detail ? `: ${p.event_detail}` : ""}` : p.error || "Failed"}
                                </p>
                            </li>
                        ))}
                    </ul>
                </Card>
            )}
        </div>
    );
}
