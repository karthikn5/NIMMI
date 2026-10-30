"use client";

import { Suspense } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Button, EmptyState, Notice, Segmented, Select, Skeleton } from "@/components/ui";
import { PlanNeeded, useLimits } from "@/lib/plan";
import { useApi } from "@/lib/useApi";
import type { ScheduleSettingsView, VoiceAgentSummary } from "@/lib/voice/types";
import { CallsPanel } from "@/components/voice/schedule/Calls";
import { MeetingsPanel } from "@/components/voice/schedule/Meetings";
import { OverviewPanel } from "@/components/voice/schedule/Overview";
import { ScheduleSettingsForm } from "@/components/voice/schedule/SettingsForm";

type Tab = "overview" | "meetings" | "calls" | "settings";
const TABS: { value: Tab; label: string }[] = [
    { value: "overview", label: "Coming up" }, { value: "meetings", label: "Meetings" },
    { value: "calls", label: "Calls" }, { value: "settings", label: "Settings" },
];

/** Call-backs, follow-ups and meetings: what the assistants arrange after a conversation (backend voice/schedule.py). */
export default function SchedulePage() {
    return (
        <Suspense fallback={<Skeleton className="h-96" />}>
            <Schedule />
        </Suspense>
    );
}

function Schedule() {
    const router = useRouter();
    const pathname = usePathname();
    const params = useSearchParams();
    const tab = (TABS.find((t) => t.value === params.get("tab"))?.value ?? "overview") as Tab;
    const bot = params.get("bot") ?? "";
    const agents = useApi<VoiceAgentSummary[]>("/api/voice/agents");
    const many = (agents.data?.length ?? 0) > 1;
    const settingsBot = bot || agents.data?.[0]?.bot_id || "";
    const setup = useApi<ScheduleSettingsView>(tab === "overview" && settingsBot ? `/api/voice/schedule/settings/${settingsBot}` : null);
    const off = tab === "overview" && setup.data && !setup.data.settings.callbacks.enabled && !setup.data.settings.follow_ups.enabled
        && !setup.data.settings.meetings.enabled;
    const limits = useLimits();
    const proNeeded = settingsBot ? limits?.assistant_plans?.[settingsBot]?.schedule === false : limits?.includes?.schedule === false;

    const go = (changes: Record<string, string | null>) => {
        const next = new URLSearchParams(params.toString());
        for (const [key, value] of Object.entries(changes)) {
            if (value) next.set(key, value);
            else next.delete(key);
        }
        const query = next.toString();
        router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    };

    return (
        <>
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-3 mb-5">
                <div>
                    <h2 className="text-[15px] font-semibold">Schedule</h2>
                    <p className="text-[13px] text-stone-500 mt-0.5 max-w-2xl">
                        Call-backs callers ask for, follow-ups after each call by how interested they sounded, and meetings with your
                        team. The assistant makes the calls; you approve what matters.
                    </p>
                </div>
                {many && (
                    <Select aria-label="Assistant" className="w-auto" value={tab === "settings" ? settingsBot : bot}
                            onChange={(e) => go({ bot: e.target.value || null })}>
                        {tab !== "settings" && <option value="">All assistants</option>}
                        {agents.data!.map((a) => <option key={a.bot_id} value={a.bot_id}>{a.bot_name}</option>)}
                    </Select>
                )}
            </div>
            {proNeeded && (
                <PlanNeeded feature="schedule" botId={settingsBot || undefined} className="mb-5">
                    {many ? "This assistant's" : "Your assistant's"} call-backs, follow-up calls and meeting calls come with Pro. Choose it on the Billing page.
                </PlanNeeded>
            )}

            <div className="mb-6 overflow-x-auto">
                <Segmented label="Schedule sections" value={tab} options={TABS}
                           onChange={(v) => go({ tab: v === "overview" ? null : v, meeting: null, item: null })} />
            </div>

            {off && (
                <Notice title={`Schedule is off${many ? ` for ${agents.data!.find((a) => a.bot_id === settingsBot)?.bot_name}` : ""}`}
                        action={<Button size="sm" variant="primary" onClick={() => go({ tab: "settings" })}>Set it up</Button>}>
                    Turn on call-backs, follow-ups or meetings, and the assistant starts arranging them on its calls.
                </Notice>
            )}

            {tab === "overview" && <OverviewPanel botId={bot} showBot={many && !bot} />}
            {tab === "meetings" && <MeetingsPanel botId={bot} showBot={many && !bot} openId={params.get("meeting")} onOpen={(id) => go({ meeting: id })} />}
            {tab === "calls" && <CallsPanel botId={bot} showBot={many && !bot} openId={params.get("item")} onOpen={(id) => go({ item: id })} />}
            {tab === "settings" && (
                settingsBot ? <ScheduleSettingsForm key={settingsBot} botId={settingsBot} />
                    : agents.loading ? <Skeleton className="h-96" />
                    : <EmptyState title="No assistants yet" body="Create an assistant first; each one has its own Schedule settings." />
            )}
        </>
    );
}
