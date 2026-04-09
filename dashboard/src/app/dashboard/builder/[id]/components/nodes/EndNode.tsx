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
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-rose-500/20 border-rose-500 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-rose-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-rose-50 border-b border-rose-100/50 flex items-center gap-2">
                <Flag size={14} className="text-rose-600" />
                <span className="text-[10px] font-black text-rose-700 uppercase tracking-widest">{data.label}</span>
            </div>
            <div className="p-5">
                 <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2 opacity-50">Closing Message</p>
                <p className="text-sm font-bold text-slate-700 leading-relaxed italic opacity-80 line-clamp-3">"{data.message || "Thank you for your time!"}"</p>
            </div>
        </div>
    );
}
