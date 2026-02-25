"use client";

import { Handle, Position } from "reactflow";
import { Phone } from "lucide-react";

export default function PhoneInputNode({ data }: { data: any }) {
    return (
        <div className="w-64 bg-[#1a1a1a] border-2 border-green-500/50 rounded-2xl p-4 shadow-2xl">
            <div className="flex items-center gap-3 mb-3 pb-3 border-b border-white/5">
                <div className="w-8 h-8 bg-green-500/10 rounded-lg flex items-center justify-center">
                    <Phone size={14} className="text-green-400" />
                </div>
                <span className="text-xs font-bold text-white/70 uppercase tracking-widest">{data.label || "Phone Input"}</span>
            </div>

            <div className="space-y-2">
                <p className="text-[10px] text-white/30 uppercase font-bold tracking-tighter">Placeholder</p>
                <div className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-[10px] text-white/40 italic">
                    {data.placeholder || "Enter phone number..."}
                </div>
            </div>

            <Handle type="target" position={Position.Top} className="!bg-green-500 !w-3 !h-3 !border-4 !border-[#1a1a1a]" />
            <Handle type="source" position={Position.Bottom} className="!bg-green-500 !w-3 !h-3 !border-4 !border-[#1a1a1a]" />
        </div>
    );
}
