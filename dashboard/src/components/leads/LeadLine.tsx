"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { Status } from "@/components/ui";
import { STAGES, formatDue, sourceLabel, type LeadRow } from "@/lib/leads";

/** One lead in a list: who, where they came from, the next step and when. */
export function LeadLine({ lead, showBot }: { lead: LeadRow; showBot?: boolean }) {
    const due = lead.next?.due_at;
    const late = !!due && new Date(due).getTime() < Date.now();
    return (
        <li className="border-t border-line first:border-t-0">
            <Link href={`/dashboard/leads/${lead.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-paper/70 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-plum">
                <span className="min-w-0 flex-1">
                    <span className="block text-sm truncate">{lead.name || lead.phone || lead.email}</span>
                    <span className="block text-[13px] text-stone-500 truncate">
                        {[lead.name ? lead.phone || lead.email : null, sourceLabel(lead.source), showBot ? lead.bot_name : null, lead.owner].filter(Boolean).join(" · ")}
                    </span>
                    {lead.next && <span className="block text-[13px] text-stone-700 truncate mt-0.5">{lead.next.title}{due ? ` · ${formatDue(due)}` : ""}</span>}
                </span>
                {late ? <Status tone="bad">Overdue</Status> : <span className="hidden sm:inline text-[13px] text-stone-500 whitespace-nowrap">{STAGES[lead.stage] ?? lead.stage}</span>}
                <ChevronRight size={15} className="text-stone-400 shrink-0" aria-hidden />
            </Link>
        </li>
    );
}
