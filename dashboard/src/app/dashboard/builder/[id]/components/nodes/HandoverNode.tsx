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
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-purple-500/20 border-purple-500 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-purple-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-purple-50 border-b border-purple-100/50 flex items-center gap-2">
                <UserPlus size={14} className="text-purple-600" />
                <span className="text-[10px] font-black text-purple-700 uppercase tracking-widest">{data.label || "Live Handover"}</span>
            </div>
            <div className="p-5">
                <p className="text-sm font-bold text-slate-700 leading-relaxed mb-2">Transferring to human agent...</p>
                <p className="text-xs text-slate-500 line-clamp-2 italic">"{data.message || "Please wait while I connect you to a human agent."}"</p>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-4 !h-4 !bg-purple-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
        </div>
    );
}
