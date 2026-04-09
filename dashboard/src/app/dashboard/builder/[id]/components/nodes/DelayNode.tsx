"use client";

import { Handle, Position } from "reactflow";
import { Clock } from "lucide-react";

interface DelayNodeProps {
    data: {
        label?: string;
        delay?: number;
    };
    selected?: boolean;
}

export default function DelayNode({ data, selected }: DelayNodeProps) {
    return (
        <div
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-slate-400/20 border-slate-400 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-slate-400 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-slate-50 border-b border-slate-100 flex items-center gap-2">
                <Clock size={14} className="text-slate-600" />
                <span className="text-[10px] font-black text-slate-700 uppercase tracking-widest">{data.label || "Time Delay"}</span>
            </div>
            <div className="p-5 flex flex-col items-center gap-3">
                 <div className="w-12 h-12 bg-slate-50 rounded-full flex items-center justify-center border border-slate-100 shadow-inner group">
                    <Clock size={20} className="text-slate-300 group-hover:text-slate-600 transition-colors" />
                </div>
                <div className="flex items-baseline gap-1">
                    <span className="text-2xl font-black text-slate-900">{data.delay || 3}</span>
                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">seconds</span>
                </div>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-4 !h-4 !bg-slate-400 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
        </div>
    );
}
