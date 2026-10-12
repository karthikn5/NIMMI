import type { ReactNode } from "react";
import type { CampaignStatus, CampaignSummary } from "@/lib/voice/types";

/** Text with {{placeholders}} shown as small tags, e.g. in a greeting or a campaign's purpose. */
export function WithPlaceholders({ text }: { text: string }) {
    const parts: ReactNode[] = [];
    let last = 0;
    for (const m of text.matchAll(/\{\{\s*([\w .-]+?)\s*\}\}/g)) {
        parts.push(text.slice(last, m.index));
        parts.push(<span key={m.index} className="inline-block px-1 rounded bg-plum-tint text-plum text-[0.92em]">{m[1]}</span>);
        last = (m.index ?? 0) + m[0].length;
    }
    parts.push(text.slice(last));
    return <>{parts}</>;
}

export const CAMPAIGN_STATUS: Record<CampaignStatus, { label: string; tone: "good" | "neutral" | "warn" | "plum" }> = {
    running: { label: "Calling", tone: "plum" },
    paused: { label: "Paused", tone: "warn" },
    completed: { label: "Finished", tone: "good" },
    cancelled: { label: "Stopped", tone: "neutral" },
};

/** "12 of 40 called" with a thin bar: reached in plum, not reached in stone. */
export function CampaignProgress({ counts }: { counts: CampaignSummary["counts"] }) {
    const total = Math.max(1, counts.total);
    const finished = counts.done + counts.failed + counts.cancelled;
    return (
        <div>
            <div className="flex justify-between text-xs text-stone-500 mb-1.5 tabular-nums">
                <span>{finished} of {counts.total} called</span>
                <span>{counts.done} reached{counts.successful ? ` · ${counts.successful} goal met` : ""}</span>
            </div>
            <div className="h-1.5 rounded-full bg-stone-100 overflow-hidden flex" aria-hidden>
                <div className="bg-plum" style={{ width: `${(counts.done / total) * 100}%` }} />
                <div className="bg-stone-300" style={{ width: `${((counts.failed + counts.cancelled) / total) * 100}%` }} />
            </div>
        </div>
    );
}
