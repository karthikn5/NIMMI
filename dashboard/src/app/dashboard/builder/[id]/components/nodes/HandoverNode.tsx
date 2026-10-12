"use client";

import { Handle, Position } from "reactflow";
import { UserPlus } from "lucide-react";

interface HandoverNodeProps {
    data: { label: string; message: string };
    selected: boolean;
}

export default function HandoverNode({ data, selected }: HandoverNodeProps) {
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
                <UserPlus size={14} className="text-plum" />
                <span className="text-[12px] font-medium text-ink">{data.label || "Live Handover"}</span>
            </div>
            <div className="p-5">
                <p className="text-sm font-normal text-slate-700 leading-relaxed mb-2">Transferring to human agent...</p>
                <p className="text-xs text-slate-500 line-clamp-2 italic">"{data.message || "Please wait while I connect you to a human agent."}"</p>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-3 !h-3 !bg-stone-400 !border-2 !border-white transition-transform hover:scale-125"
            />
        </div>
    );
}
