"use client";

import Link from "next/link";
import { Card, Skeleton, Status } from "@/components/ui";
import { useApi } from "@/lib/useApi";
import type { ScheduleSettingsView } from "@/lib/voice/types";

/** On an agent's page: what it may arrange on its calls (Voice > Schedule), with a link to change it. */
export function ScheduleCard({ botId, modelCanRun = true, modelName }: { botId: string; modelCanRun?: boolean; modelName?: string }) {
    const view = useApi<ScheduleSettingsView>(`/api/voice/schedule/settings/${botId}`);
    const s = view.data?.settings;
    const rows = s ? [
        { label: "Call-backs when asked", on: s.callbacks.enabled },
        { label: s.follow_ups.review ? "Follow-ups, after your OK" : "Follow-ups by lead rating", on: s.follow_ups.enabled },
        { label: s.meetings.approval ? "Meetings, after your OK" : "Meetings, confirmed on the call", on: s.meetings.enabled },
    ] : [];

    return (
        <Card className="p-5 mt-4">
            <h3 className="text-[15px] font-semibold">Schedule</h3>
            <p className="text-[13px] text-stone-600 mt-1.5 leading-relaxed">What this assistant may arrange on its calls, for both agents.</p>
            {!s ? <Skeleton className="h-16 mt-3" /> : (
                <ul className="mt-3 space-y-1.5">
                    {rows.map((r) => <li key={r.label}><Status tone={r.on ? "good" : "neutral"}>{r.label}: {r.on ? "on" : "off"}</Status></li>)}
                </ul>
            )}
            {s && !modelCanRun && (s.callbacks.enabled || s.meetings.enabled) && (
                <p className="text-xs text-amber-800 mt-3 leading-relaxed">
                    {modelName ?? "This agent's AI model"} can&apos;t book call-backs or meetings, so with these on its turns are answered by
                    the backup models. Choose another model to have it answer itself.
                </p>
            )}
            <Link href={`/dashboard/voice/schedule?tab=settings&bot=${botId}`} className="inline-block mt-3 text-[13px] text-plum hover:underline underline-offset-4">
                Schedule settings
            </Link>
        </Card>
    );
}
