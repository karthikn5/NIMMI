"use client";

import { Handle, Position } from "reactflow";
import { Flag } from "lucide-react";

interface EndNodeProps {
    data: { label: string; message: string };
    selected: boolean;
}

export default function EndNode({ data, selected }: EndNodeProps) {
    return (
        <div
            className={`w-64 rounded-lg bg-white border border-line-strong overflow-hidden shadow-[0_1px_3px_rgba(28,23,25,0.08)] transition-all ${selected ? "ring-2 ring-plum/20 border-plum" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-3 !h-3 !bg-rose-500 !border-2 !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-stone-50/70 border-b border-line flex items-center gap-2">
                <Flag size={14} className="text-rose-600" />
                <span className="text-[12px] font-medium text-ink">{data.label}</span>
            </div>
            <div className="p-5">
                 <p className="text-xs font-normal text-slate-500 mb-2 opacity-50">Closing Message</p>
                <p className="text-sm font-normal text-slate-700 leading-relaxed line-clamp-3">"{data.message || "Thank you for your time!"}"</p>
            </div>
        </div>
    );
}
