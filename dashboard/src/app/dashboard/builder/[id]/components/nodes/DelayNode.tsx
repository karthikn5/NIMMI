"use client";

import { Handle, Position } from "reactflow";
import { Clock } from "lucide-react";

export default function DelayNode({ data }: { data: any }) {
    return (
        <div className="w-64 bg-[#1a1a1a] border-2 border-white/30 rounded-2xl p-4 shadow-2xl">
            <div className="flex items-center gap-3 mb-3 pb-3 border-b border-white/5">
                <div className="w-8 h-8 bg-white/5 rounded-lg flex items-center justify-center">
                    <Clock size={14} className="text-white" />
                </div>
                <span className="text-xs font-bold text-white/70 uppercase tracking-widest">{data.label || "Delay"}</span>
            </div>

            <div className="text-center bg-white/5 rounded-lg py-2">
                <span className="text-xl font-bold text-white">{data.delay || 2}s</span>
                <p className="text-[10px] text-white/30 uppercase mt-1">Waiting Time</p>
            </div>

            <Handle type="target" position={Position.Top} className="!bg-white !w-3 !h-3 !border-4 !border-[#1a1a1a]" />
            <Handle type="source" position={Position.Bottom} className="!bg-white !w-3 !h-3 !border-4 !border-[#1a1a1a]" />
        </div>
    );
}
