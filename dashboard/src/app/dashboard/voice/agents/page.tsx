"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronRight, PhoneIncoming, PhoneOutgoing } from "lucide-react";
import { Button, Card, EmptyState, Segmented, Skeleton, Status } from "@/components/ui";
import { useApi } from "@/lib/useApi";
import { DIRECTIONS, directionOf, formatNumber, languageLabel } from "@/lib/voice/api";
import type { AgentDirection, Voice, VoiceAgentSummary } from "@/lib/voice/types";

export default function AgentsPage() {
    return <Suspense><Agents /></Suspense>;
}

function Agents() {
    const router = useRouter();
    const direction = directionOf(useSearchParams().get("direction"));
    const agents = useApi<VoiceAgentSummary[]>(`/api/voice/agents?direction=${direction}`);
    const voices = useApi<Voice[]>("/api/voice/voices");
    const voiceName = (id: string | null) => voices.data?.find((v) => v.id === id)?.name ?? null;
    const about = DIRECTIONS[direction];

    return (
        <>
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3 mb-4">
                <div>
                    <h2 className="text-[15px] font-semibold">{about.label}</h2>
                    <p className="text-[13px] text-stone-500 mt-0.5 max-w-xl">{about.about}</p>
                </div>
                <Segmented<AgentDirection>
                    label="Which agents"
                    value={direction}
                    onChange={(d) => router.replace(`/dashboard/voice/agents?direction=${d}`)}
                    options={[
                        { value: "inbound", label: "Incoming", icon: <PhoneIncoming size={13} /> },
                        { value: "outbound", label: "Outgoing", icon: <PhoneOutgoing size={13} /> },
                    ]}
                />
            </div>

            <Card>
                {agents.loading ? (
                    <div className="p-5 space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>
                ) : agents.error ? (
                    <p className="p-5 text-sm text-signal">Couldn&apos;t load agents. {agents.error}</p>
                ) : !agents.data?.length ? (
                    <EmptyState
                        title="No assistants yet"
                        body="Create a chat assistant first. You can turn on voice for it here."
                        action={<Link href="/dashboard"><Button variant="primary">Go to assistants</Button></Link>}
                    />
                ) : (
                    <table className="w-full text-sm">
                        <thead className="hidden md:table-header-group">
                            <tr className="text-left text-[13px] text-stone-500">
                                <th className="font-normal px-5 py-3">Assistant</th>
                                <th className="font-normal px-3 py-3">Voice</th>
                                <th className="font-normal px-3 py-3">Language</th>
                                <th className="font-normal px-3 py-3">Phone number</th>
                                <th className="font-normal px-3 py-3 text-right">Calls, 30 days</th>
                                <th className="w-10" />
                            </tr>
                        </thead>
                        <tbody>
                            {agents.data.map((a) => (
                                <tr key={a.bot_id} className="group border-t border-line first:border-t-0 md:first:border-t hover:bg-stone-50 transition-colors relative">
                                    <td className="px-5 py-3.5">
                                        <Link href={`/dashboard/voice/agents/${a.bot_id}?direction=${direction}`} className="font-medium after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-plum focus-visible:after:-outline-offset-2">
                                            {a.bot_name}
                                        </Link>
                                        <div className="mt-1">
                                            {a.enabled ? <Status tone="good">{about.on}</Status> : <Status tone="neutral">Off</Status>}
                                        </div>
                                        {/* Compact details for small screens */}
                                        <p className="md:hidden text-[13px] text-stone-500 mt-1.5">
                                            {[voiceName(a.voice_id) ?? "No voice chosen", languageLabel(a.language), a.phone_number].filter(Boolean).join(" · ")}
                                        </p>
                                    </td>
                                    <td className="hidden md:table-cell px-3 py-3.5 text-stone-700">{voiceName(a.voice_id) ?? <span className="text-stone-400">Not chosen</span>}</td>
                                    <td className="hidden md:table-cell px-3 py-3.5 text-stone-700">{languageLabel(a.language)}</td>
                                    <td className="hidden md:table-cell px-3 py-3.5 tabular-nums text-stone-700">{a.phone_number ?? <span className="text-stone-400">Browser only</span>}</td>
                                    <td className="hidden md:table-cell px-3 py-3.5 text-right tabular-nums">{formatNumber(a.calls_30d)}</td>
                                    <td className="px-3 py-3.5 text-right"><ChevronRight size={16} className="inline text-stone-300 group-hover:text-stone-500" aria-hidden /></td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </Card>
        </>
    );
}
