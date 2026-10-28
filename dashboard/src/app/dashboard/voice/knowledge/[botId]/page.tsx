"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, BookOpen, PhoneIncoming, PhoneOutgoing } from "lucide-react";
import PrimaryKnowledge from "@/components/voice/PrimaryKnowledge";
import ScriptEditor from "@/components/voice/ScriptEditor";
import { Card, Segmented, Select, cn } from "@/components/ui";
import { useApi } from "@/lib/useApi";
import type { VoiceAgentSummary } from "@/lib/voice/types";

type Section = "knowledge" | "inbound" | "outbound";
const sectionOf = (value: string | null): Section => (value === "inbound" || value === "outbound" ? value : "knowledge");

export default function KnowledgePage() {
    return <Suspense><Knowledge /></Suspense>;
}

/** Everything an assistant knows and says: its knowledge (shared with chat and WhatsApp), and its scripts for
 * incoming and outgoing calls. */
function Knowledge() {
    const { botId } = useParams<{ botId: string }>();
    const router = useRouter();
    const section = sectionOf(useSearchParams().get("section"));
    const agents = useApi<VoiceAgentSummary[]>("/api/voice/agents");
    const bot = agents.data?.find((a) => a.bot_id === botId);
    const multi = (agents.data?.length ?? 0) > 1;
    const go = (bot: string, to: Section) => router.replace(`/dashboard/voice/knowledge/${bot}?section=${to}`);

    return (
        <>
            <Link href="/dashboard/voice/knowledge" className="inline-flex items-center gap-1.5 text-[13px] text-stone-500 hover:text-ink">
                <ArrowLeft size={14} /> Knowledge
            </Link>

            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mt-3 mb-6">
                <div className="flex flex-wrap items-center gap-3">
                    {/* With several assistants, the switcher is the title. */}
                    <h2 className={cn("text-xl font-semibold tracking-tight", multi && "sr-only")}>{bot?.bot_name ?? "Assistant"}</h2>
                    {multi && (
                        <Select aria-label="Assistant" className="w-auto text-base font-semibold" value={botId} onChange={(e) => go(e.target.value, section)}>
                            {agents.data?.map((a) => <option key={a.bot_id} value={a.bot_id}>{a.bot_name}</option>)}
                        </Select>
                    )}
                </div>
                <Segmented<Section>
                    label="Section"
                    value={section}
                    onChange={(s) => go(botId, s)}
                    options={[
                        { value: "knowledge", label: "Primary knowledge", icon: <BookOpen size={13} /> },
                        { value: "inbound", label: "Incoming script", icon: <PhoneIncoming size={13} /> },
                        { value: "outbound", label: "Outgoing script", icon: <PhoneOutgoing size={13} /> },
                    ]}
                />
            </div>

            {section === "knowledge" ? (
                <>
                    <p className="text-[13px] text-stone-500 mb-4 max-w-2xl">
                        What the assistant knows, for calls, website chat and WhatsApp alike. It&apos;s the same as the Knowledge tab in the
                        assistant builder: a change here shows there, and the other way round.
                    </p>
                    <Card className="p-5 sm:p-6 max-w-2xl"><PrimaryKnowledge key={botId} botId={botId} /></Card>
                </>
            ) : (
                <div className="max-w-3xl"><ScriptEditor key={`${botId}-${section}`} botId={botId} direction={section} /></div>
            )}
        </>
    );
}
