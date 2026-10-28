"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { Button, Card, EmptyState, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/useApi";
import type { VoiceAgentSummary } from "@/lib/voice/types";

/** Pick the assistant whose knowledge and call scripts to edit (straight to it when there's only one). */
export default function KnowledgePickerPage() {
    const router = useRouter();
    const agents = useApi<VoiceAgentSummary[]>("/api/voice/agents");

    useEffect(() => {
        if (agents.data?.length === 1) router.replace(`/dashboard/voice/knowledge/${agents.data[0].bot_id}`);
    }, [agents.data, router]);

    return (
        <>
            <div className="mb-4">
                <h2 className="text-[15px] font-semibold">Knowledge</h2>
                <p className="text-[13px] text-stone-500 mt-0.5 max-w-xl">
                    What each assistant knows, and what it says on incoming and outgoing calls.
                </p>
            </div>
            <Card>
                {agents.loading ? (
                    <div className="p-5 space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>
                ) : agents.error ? (
                    <p className="p-5 text-sm text-signal">Couldn&apos;t load your assistants. {agents.error}</p>
                ) : !agents.data?.length ? (
                    <EmptyState
                        title="No assistants yet"
                        body="Create a chat assistant first. Its knowledge is shared with its voice agents."
                        action={<Link href="/dashboard"><Button variant="primary">Go to assistants</Button></Link>}
                    />
                ) : (
                    <ul>
                        {agents.data.map((a) => (
                            <li key={a.bot_id} className="border-t border-line first:border-t-0">
                                <Link href={`/dashboard/voice/knowledge/${a.bot_id}`}
                                      className="group flex items-center justify-between px-5 py-4 hover:bg-stone-50 focus-visible:outline-2 focus-visible:outline-plum focus-visible:-outline-offset-2">
                                    <span className="font-medium text-sm">{a.bot_name}</span>
                                    <ChevronRight size={16} className="text-stone-300 group-hover:text-stone-500" aria-hidden />
                                </Link>
                            </li>
                        ))}
                    </ul>
                )}
            </Card>
        </>
    );
}
