"use client";

import { useEffect, useState } from "react";
import { RatesTable } from "@/components/voice/RatesTable";
import { apiUrl } from "@/lib/api";
import type { RateCard } from "@/lib/voice/types";

/** The public rate card, read from the server so the website always shows the current rates. */
export default function CallRates() {
    const [card, setCard] = useState<RateCard | null>(null);
    const [failed, setFailed] = useState(false);

    useEffect(() => {
        fetch(apiUrl("/api/voice/rates"))
            .then((r) => (r.ok ? r.json() : Promise.reject()))
            .then(setCard)
            .catch(() => setFailed(true));
    }, []);

    if (failed) {
        return (
            <p className="text-[14px] text-stone-600 mt-4">
                Every call minute is 1 credit for the voice and phone line, plus the AI model you choose for the agent.
            </p>
        );
    }
    return card ? <div className="mt-4"><RatesTable card={card} preview /></div> : <div className="mt-4 h-56 rounded-lg bg-stone-100 animate-pulse" />;
}
