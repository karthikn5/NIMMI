"use client";

import { Handle, Position } from "reactflow";
import { Globe } from "lucide-react";

interface HttpRequestNodeProps {
    data: any;
    selected?: boolean;
}

export default function HttpRequestNode({ data, selected }: HttpRequestNodeProps) {
    return (
        <div
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-emerald-500/20 border-emerald-500 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-emerald-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-emerald-50 border-b border-emerald-100/50 flex items-center gap-2">
                <Globe size={14} className="text-emerald-600" />
                <span className="text-[10px] font-black text-emerald-700 uppercase tracking-widest">{data.label || "API Request"}</span>
            </div>
            <div className="p-5 space-y-3">
                <div className="flex items-center gap-2">
                    <div className="px-2 py-1 bg-emerald-100/50 rounded-lg text-[10px] font-bold text-emerald-700 uppercase tracking-tighter shadow-sm">{data.method || "POST"}</div>
                    <span className="text-[10px] font-mono font-bold text-slate-400 truncate flex-1 uppercase tracking-tighter">Endpoint</span>
                </div>
                <div className="w-full bg-slate-50 border border-slate-100 rounded-xl px-4 py-3 text-xs text-slate-600 font-mono font-bold truncate shadow-inner">
                    {data.url || "https://api.example.com/..."}
                </div>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-4 !h-4 !bg-emerald-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
        </div>
    );
}
