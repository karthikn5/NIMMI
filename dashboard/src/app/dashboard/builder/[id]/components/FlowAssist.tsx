"use client";

import { useState } from "react";
import type { Edge, Node } from "reactflow";
import { AlertTriangle, Check, ChevronDown, LayoutTemplate } from "lucide-react";
import { cn } from "@/components/ui";
import { TEMPLATES, type Issue } from "./flowKit";

/** "Things to fix" for the flow; each item jumps to its block. */
export function FlowChecks({ issues, onPick }: { issues: Issue[]; onPick: (nodeId: string) => void }) {
    const [open, setOpen] = useState(false);
    if (!issues.length) {
        return (
            <span className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md border border-line bg-white text-[13px] text-stone-600">
                <Check size={14} className="text-emerald-600" /> No problems found
            </span>
        );
    }
    return (
        <div className="relative">
            <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
                    className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md border border-amber-300 bg-amber-50 text-[13px] text-amber-900 hover:bg-amber-100">
                <AlertTriangle size={14} /> {issues.length} {issues.length === 1 ? "thing" : "things"} to fix
                <ChevronDown size={14} className={cn("transition-transform", open && "rotate-180")} />
            </button>
            {open && (
                <ul className="absolute left-0 top-10 z-10 w-80 max-h-80 overflow-y-auto rounded-md border border-line bg-white shadow-[0_8px_30px_rgba(28,23,25,0.12)] divide-y divide-line">
                    {issues.map((issue, i) => (
                        <li key={`${issue.nodeId}-${i}`}>
                            <button type="button" onClick={() => { onPick(issue.nodeId); setOpen(false); }}
                                    className="w-full text-left px-3 py-2.5 text-[13px] text-stone-700 hover:bg-stone-50">
                                {issue.text}
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}

/** Shown on an empty canvas: start from a ready-made flow. */
export function FlowTemplates({ onUse }: { onUse: (flow: { nodes: Node[]; edges: Edge[] }) => void }) {
    return (
        <div className="w-[min(36rem,calc(100vw-2rem))] rounded-lg border border-line bg-white p-5 shadow-[0_8px_30px_rgba(28,23,25,0.10)]">
            <div className="flex items-center gap-2">
                <LayoutTemplate size={16} className="text-stone-500" />
                <p className="text-sm font-semibold text-ink">Start from a template</p>
            </div>
            <p className="text-[13px] text-stone-500 mt-1">Or drag blocks from the left. A flow runs first, then the AI answers anything else.</p>
            <div className="grid sm:grid-cols-3 gap-2 mt-4">
                {TEMPLATES.map((t) => (
                    <button key={t.id} type="button" onClick={() => onUse(t.build())}
                            className="text-left rounded-md border border-line-strong p-3 hover:border-plum hover:bg-plum-tint/40 transition-colors">
                        <span className="block text-[13px] font-medium text-ink">{t.name}</span>
                        <span className="block text-[12px] text-stone-500 mt-1 leading-snug">{t.description}</span>
                    </button>
                ))}
            </div>
        </div>
    );
}
