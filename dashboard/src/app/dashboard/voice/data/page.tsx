"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Download } from "lucide-react";
import { Button, Card, EmptyState, Notice, SectionHeader, Select, Skeleton, Status, Switch, cn } from "@/components/ui";
import { downloadCsv } from "@/lib/csv";
import { useApi } from "@/lib/useApi";
import { OUTCOMES, SENTIMENT, formatDate, formatWhen } from "@/lib/voice/api";
import type { CollectedRow, VoiceAgentSummary } from "@/lib/voice/types";

type Data = { columns: string[]; configured: boolean; rows: CollectedRow[] };

export default function CollectedDataPage() {
    const agents = useApi<VoiceAgentSummary[]>("/api/voice/agents");
    const [botId, setBotId] = useState("");
    const [days, setDays] = useState(30);
    const [tests, setTests] = useState(false);
    const [sort, setSort] = useState<"recent" | "lead">("recent");

    useEffect(() => {
        if (!botId && agents.data?.length) setBotId((agents.data.find((a) => a.enabled) ?? agents.data[0]).bot_id);
    }, [agents.data, botId]);

    const data = useApi<Data>(botId ? `/api/voice/data?bot_id=${botId}&days=${days}&include_tests=${tests}` : null);
    const rows = useMemo(() => {
        const list = data.data?.rows ?? [];
        return sort === "lead" ? [...list].sort((a, b) => (b.lead?.score ?? 0) - (a.lead?.score ?? 0)) : list;
    }, [data.data, sort]);
    const columns = data.data?.columns ?? [];
    const botName = agents.data?.find((a) => a.bot_id === botId)?.bot_name ?? "assistant";

    const stats = useMemo(() => {
        const judged = rows.filter((r) => r.successful !== null);
        const moods = rows.filter((r) => r.sentiment);
        return {
            calls: rows.length,
            goal: judged.length ? Math.round((judged.filter((r) => r.successful).length / judged.length) * 100) : null,
            positive: moods.length ? Math.round((moods.filter((r) => r.sentiment === "positive").length / moods.length) * 100) : null,
            withData: rows.filter((r) => Object.keys(r.values).length > 0).length,
        };
    }, [rows]);

    const exportCsv = () => downloadCsv(
        `${botName.replace(/\W+/g, "-").toLowerCase()}-collected-data.csv`,
        ["Date", "Caller", "Direction", "Outcome", "Lead", "Lead score", ...columns, "Goal met", "Caller mood", "Summary"],
        rows.map((r) => [
            r.started_at ? formatDate(r.started_at) : "", r.caller, r.direction, OUTCOMES[r.outcome]?.label ?? r.outcome,
            r.lead?.label ?? "", r.lead?.score ?? "",
            ...columns.map((c) => r.values[c] ?? ""),
            r.successful === null ? "" : r.successful ? "Yes" : "No", r.sentiment ? SENTIMENT[r.sentiment].label : "", r.summary,
        ]),
    );

    if (agents.loading) return <Skeleton className="h-96" />;
    if (!agents.data?.length) {
        return <Card><EmptyState title="No assistants yet" body="Create an assistant, then set what it should find out on calls." /></Card>;
    }

    return (
        <>
            <SectionHeader
                title="Collected data"
                description="What your assistants found out on each call. Choose the details on each agent's page, under Information to collect."
                action={<Button size="sm" onClick={exportCsv} disabled={!rows.length}><Download size={13} /> Export CSV</Button>}
            />

            <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-4">
                <Select aria-label="Assistant" className="sm:w-56" value={botId} onChange={(e) => setBotId(e.target.value)}>
                    {agents.data.map((a) => <option key={a.bot_id} value={a.bot_id}>{a.bot_name}</option>)}
                </Select>
                <Select aria-label="Period" className="sm:w-40" value={days} onChange={(e) => setDays(Number(e.target.value))}>
                    <option value={7}>Last 7 days</option>
                    <option value={30}>Last 30 days</option>
                    <option value={90}>Last 90 days</option>
                    <option value={365}>Last year</option>
                </Select>
                <Select aria-label="Sort" className="sm:w-44" value={sort} onChange={(e) => setSort(e.target.value as "recent" | "lead")}>
                    <option value="recent">Most recent first</option>
                    <option value="lead">Hottest leads first</option>
                </Select>
                <label className="flex items-center gap-2 text-[13px] text-stone-600 sm:ml-auto">
                    <Switch checked={tests} onChange={setTests} label="Include browser test calls" />
                    Include test calls
                </label>
            </div>

            {data.data && !data.data.configured && (
                <Notice title="This assistant isn't collecting specific details yet"
                        action={<Link href={`/dashboard/voice/agents/${botId}`}><Button size="sm">Choose fields</Button></Link>}>
                    Until you do, it saves whatever details come up, so columns can vary from call to call.
                </Notice>
            )}

            <Card className="mb-4">
                <dl className="grid grid-cols-2 md:grid-cols-4 divide-x divide-line">
                    {[
                        { label: "Calls", value: stats.calls },
                        { label: "With details", value: stats.withData },
                        { label: "Goal met", value: stats.goal === null ? "–" : `${stats.goal}%` },
                        { label: "Positive mood", value: stats.positive === null ? "–" : `${stats.positive}%` },
                    ].map((s, i) => (
                        <div key={s.label} className={cn("px-5 py-4", i >= 2 && "border-t md:border-t-0 border-line")}>
                            <dt className="text-xs text-stone-500">{s.label}</dt>
                            <dd className="text-xl font-semibold tracking-tight tabular-nums mt-1">{s.value}</dd>
                        </div>
                    ))}
                </dl>
            </Card>

            <Card>
                {data.loading ? (
                    <div className="p-5 space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-11" />)}</div>
                ) : data.error ? (
                    <p className="p-5 text-sm text-signal">Couldn&apos;t load data. {data.error}</p>
                ) : !rows.length ? (
                    <EmptyState title="Nothing collected yet" body="When this assistant takes or makes calls, what it finds out shows up here." />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="text-left text-[13px] text-stone-500 whitespace-nowrap">
                                    <th className="font-normal pl-5 pr-3 py-3">When</th>
                                    <th className="font-normal px-3 py-3">Caller</th>
                                    <th className="font-normal px-3 py-3">Outcome</th>
                                    <th className="font-normal px-3 py-3">Lead</th>
                                    {columns.map((c) => <th key={c} className="font-normal px-3 py-3">{c}</th>)}
                                    <th className="font-normal px-3 py-3">Goal</th>
                                    <th className="font-normal pl-3 pr-5 py-3">Mood</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((r) => (
                                    <tr key={r.call_id} className="border-t border-line hover:bg-stone-50 align-top">
                                        <td className="pl-5 pr-3 py-3 whitespace-nowrap">
                                            <Link href={`/dashboard/voice/calls?call=${r.call_id}`}
                                                  className="text-stone-700 hover:text-plum underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-plum rounded">
                                                {formatWhen(r.started_at)}
                                            </Link>
                                        </td>
                                        <td className="px-3 py-3 whitespace-nowrap tabular-nums">
                                            {r.caller}
                                            {r.channel === "browser" && <span className="block text-xs text-stone-500">Test</span>}
                                        </td>
                                        <td className="px-3 py-3 whitespace-nowrap">
                                            <Status tone={OUTCOMES[r.outcome]?.tone ?? "neutral"}>{OUTCOMES[r.outcome]?.label ?? r.outcome}</Status>
                                        </td>
                                        <td className="px-3 py-3 whitespace-nowrap" title={r.lead?.reasons.join(", ")}>
                                            {r.lead && <Status tone={r.lead.label === "hot" ? "bad" : r.lead.label === "warm" ? "warn" : "neutral"}>
                                                {r.lead.label === "hot" ? "Hot" : r.lead.label === "warm" ? "Warm" : "Cold"} <span className="text-stone-400 tabular-nums">{r.lead.score}</span>
                                            </Status>}
                                        </td>
                                        {columns.map((c) => (
                                            <td key={c} className="px-3 py-3 max-w-56">
                                                {r.values[c] ? <span className="line-clamp-2">{r.values[c]}</span> : <span className="text-stone-300">–</span>}
                                            </td>
                                        ))}
                                        <td className="px-3 py-3 whitespace-nowrap">
                                            {r.successful === null ? <span className="text-stone-300">–</span>
                                                : <Status tone={r.successful ? "good" : "neutral"}>{r.successful ? "Met" : "Not met"}</Status>}
                                        </td>
                                        <td className="pl-3 pr-5 py-3 whitespace-nowrap">
                                            {r.sentiment ? <Status tone={SENTIMENT[r.sentiment].tone}>{SENTIMENT[r.sentiment].label}</Status> : <span className="text-stone-300">–</span>}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Card>
        </>
    );
}
