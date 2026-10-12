"use client";

import { Handle, Position } from "reactflow";
import { MessageSquare } from "lucide-react";

interface MessageNodeProps {
    data: { label: string; message: string };
    selected: boolean;
}

export default function MessageNode({ data, selected }: MessageNodeProps) {
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
                <MessageSquare size={14} className="text-blue-600" />
                <span className="text-[12px] font-medium text-ink">{data.label}</span>
            </div>
            <div className="p-5">
                <p className="text-sm font-normal text-slate-700 leading-relaxed line-clamp-3">{data.message}</p>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-3 !h-3 !bg-stone-400 !border-2 !border-white transition-transform hover:scale-125"
            />
        </div>
    );
}
