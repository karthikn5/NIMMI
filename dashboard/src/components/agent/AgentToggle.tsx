"use client";

import { cn } from "@/components/ui";
import { useAgent } from "./AgentProvider";

/** The top bar's switch for Nimmi, the dashboard's agent: Violet's face, and whether the panel is open. */
export default function AgentToggle({ className }: { className?: string }) {
    const agent = useAgent();
    if (!agent) return null;
    return (
        <button
            type="button"
            onClick={agent.toggle}
            aria-pressed={agent.open}
            aria-label={agent.open ? "Close Nimmi, your dashboard assistant" : "Open Nimmi, your dashboard assistant"}
            title="Nimmi, your dashboard assistant (Ctrl + /)"
            className={cn(
                "h-9 shrink-0 inline-flex items-center gap-2 pl-1 pr-2.5 rounded-full border text-[13px] font-medium transition-colors",
                "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum",
                agent.open ? "border-plum/30 bg-plum-tint text-plum" : "border-line bg-white text-stone-600 hover:text-ink hover:border-line-strong",
                className,
            )}
        >
            <span className="relative">
                <img src="/agent/nimmi.svg" alt="" className="h-7 w-7 rounded-full" />
                <span className={cn("absolute -right-0.5 -bottom-0.5 h-2.5 w-2.5 rounded-full border-2 border-white",
                                    agent.running ? "bg-amber-500 animate-pulse" : agent.open ? "bg-emerald-500" : "bg-stone-300")} aria-hidden />
            </span>
            <span className="hidden sm:inline">Nimmi</span>
        </button>
    );
}
