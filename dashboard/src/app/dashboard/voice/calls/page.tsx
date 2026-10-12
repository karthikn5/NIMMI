"use client";

import { Suspense, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Download, PhoneIncoming, PhoneOutgoing, Search } from "lucide-react";
import {
    Button, Card, EmptyState, Input, Segmented, Select, Sheet, Skeleton, Status, cn, useToast,
} from "@/components/ui";
import { apiUrl } from "@/lib/api";
import { apiSave, useApi } from "@/lib/useApi";
import { OUTCOMES, SENTIMENT, formatDuration, formatWhen, languageLabel } from "@/lib/voice/api";
import type { CallOutcome, CallRecord } from "@/lib/voice/types";

export default function CallsPage() {
    return (
        <Suspense fallback={<Skeleton className="h-96" />}>
            <Calls />
        </Suspense>
    );
}

function Calls() {
    const router = useRouter();
    const pathname = usePathname();
    const params = useSearchParams();
    const openId = params.get("call");

    const calls = useApi<CallRecord[]>("/api/voice/calls");
    const [direction, setDirection] = useState<"all" | "inbound" | "outbound">("all");
    const [outcome, setOutcome] = useState<"all" | CallOutcome>("all");
    const [query, setQuery] = useState("");

    const rows = useMemo(() => {
        const q = query.trim().toLowerCase();
        return (calls.data ?? []).filter((c) =>
            (direction === "all" || (c.channel === "phone" && c.direction === direction)) &&
            (outcome === "all" || c.outcome === outcome) &&
            (!q || c.caller.includes(q) || c.bot_name.toLowerCase().includes(q) ||
                Object.values(c.captured ?? {}).some((v) => v.toLowerCase().includes(q))),
        );
    }, [calls.data, direction, outcome, query]);

    const openCall = (id: string | null) => router.replace(id ? `${pathname}?call=${id}` : pathname, { scroll: false });
    const filtered = direction !== "all" || outcome !== "all" || query !== "";

    return (
        <>
            <div className="flex flex-col md:flex-row md:items-center gap-3 mb-4">
                <Segmented
                    label="Direction"
                    value={direction}
                    onChange={setDirection}
                    options={[{ value: "all", label: "All" }, { value: "inbound", label: "Inbound" }, { value: "outbound", label: "Outbound" }]}
                />
                <Select aria-label="Outcome" className="md:w-44" value={outcome} onChange={(e) => setOutcome(e.target.value as typeof outcome)}>
                    <option value="all">All outcomes</option>
                    {Object.entries(OUTCOMES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </Select>
                <div className="relative md:ml-auto md:w-72">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" aria-hidden />
                    <Input aria-label="Search calls" placeholder="Search number, name or assistant" className="pl-8" value={query} onChange={(e) => setQuery(e.target.value)} />
                </div>
            </div>

            <Card>
                {calls.loading ? (
                    <div className="p-5 space-y-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-11" />)}</div>
                ) : calls.error ? (
                    <p className="p-5 text-sm text-signal">Couldn&apos;t load calls. {calls.error}</p>
                ) : rows.length === 0 ? (
                    filtered
                        ? <EmptyState title="No calls match" body="Try a different filter or search." action={<Button size="sm" onClick={() => { setDirection("all"); setOutcome("all"); setQuery(""); }}>Clear filters</Button>} />
                        : <EmptyState title="No calls yet" body="Calls show up here as soon as your assistant answers one. Try a test call from an agent's page." />
                ) : (
                    <table className="w-full text-sm">
                        <thead className="hidden md:table-header-group">
                            <tr className="text-left text-[13px] text-stone-500">
                                <th className="font-normal pl-5 pr-3 py-3">Caller</th>
                                <th className="font-normal px-3 py-3">Assistant</th>
                                <th className="font-normal px-3 py-3">Outcome</th>
                                <th className="font-normal px-3 py-3 text-right">Length</th>
                                <th className="font-normal pl-3 pr-5 py-3 text-right">When</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((c) => (
                                <tr
                                    key={c.id}
                                    onClick={() => openCall(c.id)}
                                    className={cn("border-t border-line first:border-t-0 md:first:border-t cursor-pointer hover:bg-stone-50 transition-colors", openId === c.id && "bg-plum-tint hover:bg-plum-tint")}
                                >
                                    <td className="pl-5 pr-3 py-3">
                                        <button
                                            onClick={(e) => { e.stopPropagation(); openCall(c.id); }}
                                            className="flex items-center gap-2.5 text-left rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum"
                                        >
                                            {c.direction === "inbound"
                                                ? <PhoneIncoming size={14} className="text-stone-400 shrink-0" aria-label="Inbound" />
                                                : <PhoneOutgoing size={14} className="text-stone-400 shrink-0" aria-label="Outbound" />}
                                            <span>
                                                <span className="block tabular-nums">{c.caller}</span>
                                                {(c.captured?.Name || c.direction === "outbound") && (
                                                    <span className="block text-xs text-stone-500">
                                                        {[c.captured?.Name, c.direction === "outbound" && (c.campaign_id ? "Campaign" : "Callback")].filter(Boolean).join(" · ")}
                                                    </span>
                                                )}
                                            </span>
                                        </button>
                                        <div className="md:hidden mt-1.5 ml-6 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-stone-500">
                                            <Status tone={OUTCOMES[c.outcome].tone}>{OUTCOMES[c.outcome].label}</Status>
                                            <span>{c.bot_name}</span>
                                            <span className="tabular-nums">{formatDuration(c.duration_sec)}</span>
                                            <span>{formatWhen(c.started_at)}</span>
                                        </div>
                                    </td>
                                    <td className="hidden md:table-cell px-3 py-3 text-stone-700">{c.bot_name}</td>
                                    <td className="hidden md:table-cell px-3 py-3">
                                        <Status tone={OUTCOMES[c.outcome].tone}>{OUTCOMES[c.outcome].label}</Status>
                                        {c.successful !== null && c.successful !== undefined && (
                                            <span className={cn("block text-xs mt-0.5 ml-3", c.successful ? "text-emerald-700" : "text-stone-500")}>
                                                {c.successful ? "Goal met" : "Goal not met"}
                                            </span>
                                        )}
                                    </td>
                                    <td className="hidden md:table-cell px-3 py-3 text-right tabular-nums text-stone-700">{formatDuration(c.duration_sec)}</td>
                                    <td className="hidden md:table-cell pl-3 pr-5 py-3 text-right text-stone-500 whitespace-nowrap">{formatWhen(c.started_at)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </Card>

            <CallSheet id={openId} onClose={() => openCall(null)} />
        </>
    );
}

function CallSheet({ id, onClose }: { id: string | null; onClose: () => void }) {
    const toast = useToast();
    const call = useApi<CallRecord>(id ? `/api/voice/calls/${id}` : null);
    const c = call.data && call.data.id === id ? call.data : null;

    const blockNumber = async () => {
        if (!c) return;
        const res = await apiSave("/api/voice/dnc", "POST", { call_id: c.id });
        toast(res.ok ? "Added to the do-not-call list" : res.message);
    };

    const downloadTranscript = () => {
        if (!c?.transcript) return;
        const mmss = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, "0")}`;
        const text = c.transcript
            .map((t) => `[${mmss(t.at_sec)}] ${t.speaker === "agent" ? "Assistant" : t.speaker === "caller" ? "Caller" : "--"}: ${t.text}`)
            .join("\n");
        const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
        const a = Object.assign(document.createElement("a"), { href: url, download: `call-${c.id}.txt` });
        a.click();
        URL.revokeObjectURL(url);
    };

    return (
        <Sheet
            open={!!id}
            onClose={onClose}
            title={c ? <span className="tabular-nums">{c.caller}</span> : "Call"}
            subtitle={c && `${c.direction === "inbound" ? "Inbound" : c.campaign_id ? "Campaign" : "Callback"} · ${c.bot_name} · ${formatWhen(c.started_at)}`}
        >
            {call.loading ? (
                <div className="p-6 space-y-3"><Skeleton className="h-16" /><Skeleton className="h-40" /></div>
            ) : !c ? (
                <EmptyState title="Call not found" body="It may have been deleted under your retention policy." />
            ) : (
                <div className="divide-y divide-line">
                    <dl className="grid grid-cols-3 gap-4 px-6 py-5">
                        <div><dt className="text-xs text-stone-500">Outcome</dt><dd className="mt-1"><Status tone={OUTCOMES[c.outcome].tone}>{OUTCOMES[c.outcome].label}</Status></dd></div>
                        <div><dt className="text-xs text-stone-500">Length</dt><dd className="mt-1 text-[13px] tabular-nums">{formatDuration(c.duration_sec)}</dd></div>
                        <div><dt className="text-xs text-stone-500">Language</dt><dd className="mt-1 text-[13px]">{languageLabel(c.language)}</dd></div>
                        {c.successful !== null && c.successful !== undefined && (
                            <div><dt className="text-xs text-stone-500">Goal</dt><dd className="mt-1"><Status tone={c.successful ? "good" : "neutral"}>{c.successful ? "Met" : "Not met"}</Status></dd></div>
                        )}
                        {c.sentiment && (
                            <div><dt className="text-xs text-stone-500">Caller mood</dt><dd className="mt-1"><Status tone={SENTIMENT[c.sentiment].tone}>{SENTIMENT[c.sentiment].label}</Status></dd></div>
                        )}
                    </dl>

                    {(c.summary || c.consent_source) && (
                        <section className="px-6 py-5 space-y-4">
                            {c.summary && <p className="text-sm leading-relaxed">{c.summary}</p>}
                            {c.consent_source && (
                                <div>
                                    <h3 className="text-xs text-stone-500">Why we called</h3>
                                    <p className="text-[13px] mt-1">{c.consent_source}</p>
                                </div>
                            )}
                        </section>
                    )}

                    {c.captured && Object.keys(c.captured).length > 0 && (
                        <section className="px-6 py-5">
                            <h3 className="text-[13px] font-medium mb-3">Details collected</h3>
                            <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 text-[13px]">
                                {Object.entries(c.captured).map(([k, v]) => (
                                    <div key={k} className="contents">
                                        <dt className="text-stone-500">{k}</dt>
                                        <dd>{v}</dd>
                                    </div>
                                ))}
                            </dl>
                        </section>
                    )}

                    {c.duration_sec > 0 && (
                        <section className="px-6 py-5">
                            <h3 className="text-[13px] font-medium mb-3">Recording</h3>
                            {c.recording_url
                                ? <audio controls src={apiUrl(c.recording_url)} className="w-full h-9" />
                                : <p className="text-[13px] text-stone-500">No recording for this call.</p>}
                        </section>
                    )}

                    {c.transcript && c.transcript.length > 0 && (
                        <section className="px-6 py-5">
                            <div className="flex items-center justify-between mb-3">
                                <h3 className="text-[13px] font-medium">Transcript</h3>
                                <Button size="sm" variant="ghost" onClick={downloadTranscript}><Download size={13} /> Download</Button>
                            </div>
                            <ol className="space-y-3">
                                {c.transcript.map((t, i) => (
                                    <li key={i} className="grid grid-cols-[2.5rem_1fr] gap-3 text-[13px] leading-relaxed">
                                        <span className="text-stone-400 tabular-nums pt-px">
                                            {Math.floor(t.at_sec / 60)}:{(t.at_sec % 60).toString().padStart(2, "0")}
                                        </span>
                                        {t.speaker === "system" ? (
                                            <span className="text-stone-500">{t.text}</span>
                                        ) : (
                                            <span>
                                                <span className={cn("block text-xs", t.speaker === "agent" ? "text-plum font-medium" : "text-stone-500")}>
                                                    {t.speaker === "agent" ? "Assistant" : "Caller"}
                                                </span>
                                                {t.text}
                                            </span>
                                        )}
                                    </li>
                                ))}
                            </ol>
                        </section>
                    )}

                    {c.outcome !== "opted_out" && (
                        <section className="px-6 py-5">
                            <Button size="sm" variant="danger" onClick={blockNumber}>Don&apos;t call this number again</Button>
                        </section>
                    )}
                </div>
            )}
        </Sheet>
    );
}
