"use client";

import { useState } from "react";
import { cn } from "@/components/ui";
import { formatNumber, formatRate } from "@/lib/voice/api";
import type { RateCard, VoiceModel } from "@/lib/voice/types";

const seconds = (n: number) => `${new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 }).format(n)} s`;
const inr = (n: number) => `₹${n.toFixed(2)}`;

/** What a call minute costs on each AI model, grouped as on the agent page. `preview` shows a few, with the rest a
 * click away (the website); otherwise all of them (Billing). */
export function RatesTable({ card, preview = false }: { card: RateCard; preview?: boolean }) {
    const [all, setAll] = useState(!preview);
    const perCredit = card.packs.map((p) => p.price / p.credits);
    const [low, high] = [Math.min(...perCredit), Math.max(...perCredit)];
    // The website shows a few a group, suggested first, then the lowest cost.
    const shown = (models: VoiceModel[]) => (all ? models : [...models].sort((a, b) =>
        Number(b.suggested) - Number(a.suggested) || a.credits_per_minute - b.credits_per_minute).slice(0, 3));
    const groups = (Object.keys(card.groups) as VoiceModel["group"][])
        .map((g) => [g, shown(card.models.filter((m) => m.group === g && m.available))] as const)
        .filter(([, models]) => models.length);
    const total = card.models.filter((m) => m.available).length;

    return (
        <div>
            <div className="overflow-x-auto rounded-lg border border-line bg-white">
                <table className="w-full min-w-[520px] text-[14px]">
                    <thead>
                        <tr className="text-left text-[12px] text-stone-500">
                            <th className="font-medium px-4 py-2.5">AI model</th>
                            <th className="font-medium px-4 py-2.5 text-right">Credits a minute</th>
                            <th className="font-medium px-4 py-2.5 text-right">Rupees a minute</th>
                            <th className="font-medium px-4 py-2.5 text-right">Starts answering</th>
                        </tr>
                    </thead>
                    {groups.map(([group, models]) => (
                        <tbody key={group}>
                            <tr>
                                <th colSpan={4} scope="colgroup"
                                    className="text-left px-4 pt-3.5 pb-1.5 border-t border-line text-[11px] font-medium uppercase tracking-[0.06em] text-stone-500">
                                    {card.groups[group]}
                                </th>
                            </tr>
                            {models.map((m) => (
                                <tr key={m.id} className="border-t border-line/70">
                                    <td className="px-4 py-2">
                                        <span className="font-medium">{m.name}</span>
                                        <span className="text-stone-500"> · {m.maker}</span>
                                        {m.preview && <span className="ml-2 text-[11px] px-1.5 rounded bg-stone-100 text-stone-600">Preview</span>}
                                    </td>
                                    <td className="px-4 py-2 text-right tabular-nums font-medium">{formatRate(m.credits_per_minute)}</td>
                                    <td className="px-4 py-2 text-right tabular-nums text-stone-600 whitespace-nowrap">
                                        {inr(m.credits_per_minute * low)} to {inr(m.credits_per_minute * high)}
                                    </td>
                                    <td className="px-4 py-2 text-right tabular-nums text-stone-600">
                                        {m.first_words_sec === null ? "Not measured" : seconds(m.first_words_sec)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    ))}
                </table>
            </div>
            <div className={cn("flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 mt-2.5 text-[13px] text-stone-500")}>
                <p>
                    Every minute includes {formatNumber(card.base_credits)} credit for the voice, speech recognition and phone line.
                    Calls are counted in half-minutes. A credit costs {inr(low)} to {inr(high)}, by pack.
                </p>
                {preview && !all && total > groups.reduce((n, [, models]) => n + models.length, 0) && (
                    <button type="button" onClick={() => setAll(true)} className="font-medium text-plum hover:underline underline-offset-4">
                        Show all {total} models
                    </button>
                )}
            </div>
        </div>
    );
}
