"use client";

import { Handle, Position } from "reactflow";
import { Play } from "lucide-react";

interface StartNodeProps {
    data: { label: string };
    selected: boolean;
}

export default function StartNode({ data, selected }: StartNodeProps) {
    return (
        <div
            className={`w-64 px-6 py-5 rounded-[24px] bg-white border border-slate-200 text-slate-900 shadow-xl transition-all ${selected ? "ring-4 ring-emerald-500/20 border-emerald-500 scale-105" : ""
                }`}
        >
            <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-emerald-500 rounded-2xl flex items-center justify-center shadow-lg shadow-emerald-500/20">
                    <Play size={18} fill="white" className="text-white" />
                </div>
                <div>
                     <p className="text-[10px] font-black text-emerald-600 uppercase tracking-widest leading-none mb-1">Entry Point</p>
                     <p className="text-sm font-black text-slate-900 uppercase tracking-tighter">{data.label}</p>
                </div>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-4 !h-4 !bg-emerald-500 !border-[3px] !border-white !shadow-md transition-transform hover:scale-125"
            />
        </div>
    );
}
