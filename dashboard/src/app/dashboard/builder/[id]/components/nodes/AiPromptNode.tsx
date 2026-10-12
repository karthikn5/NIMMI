"use client";

import { Handle, Position } from "reactflow";
import { Sparkles } from "lucide-react";

interface AiPromptNodeProps {
    data: {
        label?: string;
        prompt?: string;
    };
    selected?: boolean;
}

export default function AiPromptNode({ data, selected }: AiPromptNodeProps) {
    return (
        <div
            className={`w-64 rounded-lg bg-white border border-line-strong overflow-hidden shadow-[0_1px_3px_rgba(28,23,25,0.08)] transition-all ${selected ? "ring-2 ring-plum/20 border-plum" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-3 !h-3 !bg-stone-400 !border-2 !border-white transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-stone-50/70 border-b border-line flex items-center gap-2">
                <Sparkles size={14} className="text-cyan-600" />
                <span className="text-[12px] font-medium text-ink">{data.label || "AI Logic Step"}</span>
            </div>
            <div className="p-5">
                <div className="w-full bg-slate-50 border border-slate-100 rounded-xl px-4 py-3 text-xs text-slate-400 font-normal italic line-clamp-3 shadow-inner">
                    {data.prompt || "No AI instructions set..."}
                </div>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-3 !h-3 !bg-stone-400 !border-2 !border-white transition-transform hover:scale-125"
            />
        </div>
    );
}
