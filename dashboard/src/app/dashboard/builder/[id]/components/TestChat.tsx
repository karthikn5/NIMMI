"use client";

import { useState } from "react";
import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui";

/** The real chat widget in test mode, so knowledge and behaviour changes can be tried right away. */
export default function TestChat({ botId, saving }: { botId: string; saving: boolean }) {
    const [run, setRun] = useState(0);
    // Start over as a new visitor: forget the saved chat (including a hand-over to a person) and the visitor ID.
    const restart = () => {
        try {
            localStorage.removeItem(`nimmi_chat_history_${botId}`);
            localStorage.removeItem(`nimmi_visitor_${botId}`);
        } catch { /* storage blocked: the reload still resets the AI chat */ }
        setRun((n) => n + 1);
    };
    return (
        <div className="h-full flex flex-col">
            <div className="h-12 shrink-0 flex items-center justify-between gap-3 px-4 border-b border-line bg-white/70">
                <div className="min-w-0">
                    <p className="text-[13px] font-medium text-ink">Test your assistant</p>
                    <p className="text-[12px] text-stone-500 truncate">{saving ? "Saving your changes…" : "Replies use your saved knowledge and behaviour."}</p>
                </div>
                <Button size="sm" variant="ghost" onClick={restart}><RotateCcw size={14} /> Restart</Button>
            </div>
            <div className="flex-1 min-h-0 flex items-center justify-center p-5 sm:p-8">
                <div className="h-full max-h-[680px] w-full max-w-[400px] rounded-2xl overflow-hidden border border-black/5 bg-white shadow-[0_10px_40px_rgba(0,0,0,0.12)]">
                    <iframe key={run} title="Test chat" src={`/widget/${botId}?is_demo=true&run=${run}`} className="h-full w-full border-0" />
                </div>
            </div>
        </div>
    );
}
