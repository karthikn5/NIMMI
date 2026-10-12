"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Download, Pause, Play, Square } from "lucide-react";
import { Button, Card, Dialog, EmptyState, Skeleton, Status, useToast } from "@/components/ui";
import { CAMPAIGN_STATUS, CampaignProgress, WithPlaceholders } from "@/components/voice/CampaignBits";
import { downloadCsv } from "@/lib/csv";
import { apiSave, useApi } from "@/lib/useApi";
import { OUTCOMES, SENTIMENT, formatDate, formatWhen } from "@/lib/voice/api";
import type { CampaignContact, CampaignDetail } from "@/lib/voice/types";

const CONTACT_STATUS: Record<CampaignContact["status"], { label: string; tone: "good" | "neutral" | "warn" | "bad" | "plum" }> = {
    queued: { label: "Waiting", tone: "neutral" },
    calling: { label: "Calling", tone: "plum" },
    done: { label: "Reached", tone: "good" },
    failed: { label: "Not reached", tone: "bad" },
    cancelled: { label: "Skipped", tone: "neutral" },
};

export default function CampaignPage() {
    const { id } = useParams<{ id: string }>();
    const toast = useToast();
    const campaign = useApi<CampaignDetail>(`/api/voice/campaigns/${id}`);
    const [stopping, setStopping] = useState(false);
    const c = campaign.data;
    const live = c?.status === "running";

    // Refresh while calls are going out.
    const { reload } = campaign;
    useEffect(() => {
        if (!live) return;
        const t = setInterval(reload, 8000);
        return () => clearInterval(t);
    }, [live, reload]);

    const act = async (action: "pause" | "resume" | "cancel") => {
        const res = await apiSave(`/api/voice/campaigns/${id}/${action}`, "POST");
        if (!res.ok) return toast(res.message);
        toast(action === "pause" ? "Paused. Nobody new will be called." : action === "resume" ? "Calling again" : "Campaign stopped");
        setStopping(false);
        reload();
    };

    if (campaign.loading && !c) return <div className="space-y-4"><Skeleton className="h-10 w-72" /><Skeleton className="h-64" /></div>;
    if (!c) return <p className="text-sm text-signal">Couldn&apos;t load this campaign. {campaign.error}</p>;
    // The person's name already heads each row.
    const fields = c.fields.filter((f) => f.trim().toLowerCase() !== "name");

    const exportCsv = () => downloadCsv(
        `${c.name.replace(/\W+/g, "-").toLowerCase()}-results.csv`,
        ["Name", "Phone", "Status", "Attempts", "Outcome", ...c.fields, "Goal met", "Caller mood", "Summary", "Note"],
        c.contacts.map((p) => [
            p.name ?? "", p.phone, CONTACT_STATUS[p.status].label, p.attempts, p.outcome ? OUTCOMES[p.outcome]?.label : "",
            ...c.fields.map((f) => p.values[f] ?? ""),
            p.successful === null ? "" : p.successful ? "Yes" : "No", p.sentiment ? SENTIMENT[p.sentiment].label : "",
            p.summary ?? "", p.last_error ?? "",
        ]),
    );

    const stats = [
        { label: "People", value: c.counts.total },
        { label: "Reached", value: c.counts.done },
        { label: "Goal met", value: c.counts.successful },
        { label: "Not reached", value: c.counts.failed },
        { label: "Still to call", value: c.counts.queued + c.counts.calling },
    ];

    return (
        <>
            <Link href="/dashboard/voice/campaigns" className="inline-flex items-center gap-1.5 text-[13px] text-stone-500 hover:text-ink">
                <ArrowLeft size={14} /> Campaigns
            </Link>

            <div className="flex flex-wrap items-start justify-between gap-4 mt-3 mb-6">
                <div className="min-w-0">
                    <div className="flex items-center gap-3">
                        <h2 className="text-xl font-semibold tracking-tight truncate">{c.name}</h2>
                        <Status tone={CAMPAIGN_STATUS[c.status].tone}>{CAMPAIGN_STATUS[c.status].label}</Status>
                    </div>
                    <p className="text-[13px] text-stone-500 mt-1">
                        {c.bot_name} · from {c.from_number ?? "a removed number"} · {c.window_start} to {c.window_end} India time ·
                        {" "}{c.max_attempts === 1 ? "no retries" : `up to ${c.max_attempts} tries`} · started {formatDate(c.created_at)}
                    </p>
                </div>
                <div className="flex gap-2">
                    {c.status === "running" && <Button size="sm" onClick={() => act("pause")}><Pause size={13} /> Pause</Button>}
                    {c.status === "paused" && <Button size="sm" variant="primary" onClick={() => act("resume")}><Play size={13} /> Resume</Button>}
                    {(c.status === "running" || c.status === "paused") && <Button size="sm" variant="danger" onClick={() => setStopping(true)}><Square size={12} /> Stop</Button>}
                    <Button size="sm" onClick={exportCsv}><Download size={13} /> Export results</Button>
                </div>
            </div>

            <Card className="p-5 mb-4">
                <CampaignProgress counts={c.counts} />
                <dl className="grid grid-cols-2 sm:grid-cols-5 gap-4 mt-5">
                    {stats.map((s) => (
                        <div key={s.label}>
                            <dt className="text-xs text-stone-500">{s.label}</dt>
                            <dd className="text-xl font-semibold tracking-tight tabular-nums mt-0.5">{s.value}</dd>
                        </div>
                    ))}
                </dl>
                <p className="text-[13px] text-stone-600 mt-5 pt-4 border-t border-line">
                    <span className="text-stone-500">Why we&apos;re calling: </span><WithPlaceholders text={c.purpose} />
                </p>
            </Card>

            <Card>
                {!c.contacts.length ? (
                    <EmptyState title="Nobody on this list" body="Every number was invalid, repeated or on your do-not-call list." />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="text-left text-[13px] text-stone-500 whitespace-nowrap">
                                    <th className="font-normal pl-5 pr-3 py-3">Person</th>
                                    <th className="font-normal px-3 py-3">Status</th>
                                    {fields.map((f) => <th key={f} className="font-normal px-3 py-3">{f}</th>)}
                                    <th className="font-normal px-3 py-3">Goal</th>
                                    <th className="font-normal pl-3 pr-5 py-3">Notes</th>
                                </tr>
                            </thead>
                            <tbody>
                                {c.contacts.map((p) => (
                                    <tr key={p.id} className="border-t border-line align-top hover:bg-stone-50">
                                        <td className="pl-5 pr-3 py-3 whitespace-nowrap">
                                            <span className="block">{p.name || "–"}</span>
                                            <span className="block text-xs text-stone-500 tabular-nums">{p.phone}</span>
                                        </td>
                                        <td className="px-3 py-3 whitespace-nowrap">
                                            <Status tone={CONTACT_STATUS[p.status].tone}>{CONTACT_STATUS[p.status].label}</Status>
                                            <span className="block text-xs text-stone-500 mt-0.5 ml-3">
                                                {p.outcome ? OUTCOMES[p.outcome]?.label : p.status === "queued" && p.next_attempt_at ? formatWhen(p.next_attempt_at) : ""}
                                                {p.attempts > 1 ? ` · ${p.attempts} tries` : ""}
                                            </span>
                                        </td>
                                        {fields.map((f) => (
                                            <td key={f} className="px-3 py-3 max-w-48">
                                                {p.values[f] ? <span className="line-clamp-2">{p.values[f]}</span> : <span className="text-stone-300">–</span>}
                                            </td>
                                        ))}
                                        <td className="px-3 py-3 whitespace-nowrap">
                                            {p.successful === null ? <span className="text-stone-300">–</span>
                                                : <Status tone={p.successful ? "good" : "neutral"}>{p.successful ? "Met" : "Not met"}</Status>}
                                        </td>
                                        <td className="pl-3 pr-5 py-3 min-w-56 max-w-sm text-[13px] text-stone-600">
                                            {p.summary || p.last_error || ""}
                                            {p.call_id && (
                                                <Link href={`/dashboard/voice/calls?call=${p.call_id}`} className="block text-xs text-plum hover:underline underline-offset-4 mt-0.5">
                                                    Open call
                                                </Link>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Card>

            <Dialog
                open={stopping}
                onClose={() => setStopping(false)}
                title="Stop this campaign?"
                description="Calls already in progress finish normally. Everyone still waiting is skipped, and you can't restart it."
                footer={<>
                    <Button variant="ghost" onClick={() => setStopping(false)}>Keep going</Button>
                    <Button variant="danger" onClick={() => act("cancel")}>Stop campaign</Button>
                </>}
            >
                <p className="text-[13px] text-stone-600">To pause and continue later, use Pause instead.</p>
            </Dialog>
        </>
    );
}
