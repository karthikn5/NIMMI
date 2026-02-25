"use client";

import { Handle, Position } from "reactflow";
import { Globe } from "lucide-react";

export default function HttpRequestNode({ data }: { data: any }) {
    return (
        <div className="w-64 bg-[#050505] border-2 border-green-500/50 rounded-2xl p-4 shadow-2xl overflow-hidden relative group">
            <div className="absolute top-0 right-0 w-24 h-24 bg-green-500/5 blur-2xl rounded-full -mr-12 -mt-12" />

            <div className="flex items-center gap-3 mb-3 pb-3 border-b border-white/10 relative">
                <div className="w-8 h-8 bg-green-500/10 rounded-lg flex items-center justify-center">
                    <Globe size={14} className="text-green-400" />
                </div>
                <span className="text-xs font-bold text-white uppercase tracking-widest">{data.label || "External API Call"}</span>
            </div>

            <div className="space-y-2 relative">
                <div className="flex items-center justify-between px-3 py-1 bg-white/5 rounded-md">
                    <span className="text-[9px] font-bold text-green-400 uppercase tracking-widest">{data.method || "POST"}</span>
                    <span className="text-[9px] text-white/40 truncate ml-2">https://api.myapp.com/v1/...</span>
                </div>
                <p className="text-[9px] text-white/20 px-1 italic">Response stored in "api_res"</p>
            </div>

            <Handle type="target" position={Position.Top} className="!bg-green-500 !w-3 !h-3 !border-4 !border-[#050505]" />
            <Handle type="source" position={Position.Bottom} className="!bg-green-500 !w-3 !h-3 !border-4 !border-[#050505]" />
        </div>
    );
}
