"use client";

import { Handle, Position } from "reactflow";
import { Sparkles } from "lucide-react";

export default function AiPromptNode({ data }: { data: any }) {
    return (
        <div className="w-64 bg-[#050505] border-2 border-cyan-500/50 rounded-2xl p-4 shadow-2xl relative overflow-hidden group">
            <div className="absolute inset-0 bg-cyan-500/5 opacity-0 group-hover:opacity-100 transition-opacity" />

            <div className="flex items-center gap-3 mb-3 pb-3 border-b border-white/10 relative">
                <div className="w-8 h-8 bg-cyan-500/10 rounded-lg flex items-center justify-center">
                    <Sparkles size={14} className="text-cyan-400" />
                </div>
                <span className="text-xs font-bold text-white uppercase tracking-widest">{data.label || "AI Logic Step"}</span>
            </div>

            <div className="space-y-2 relative">
                <p className="text-[10px] font-bold text-cyan-400/50 uppercase tracking-widest">System Instruction</p>
                <div className="bg-black/40 border border-white/10 rounded-xl p-3 text-[10px] text-white/60 line-clamp-3 leading-relaxed">
                    {data.prompt || "Analyze the last user message and determine if they want to speak to a human representative..."}
                </div>
            </div>

            <Handle type="target" position={Position.Top} className="!bg-cyan-500 !w-3 !h-3 !border-4 !border-[#050505]" />
            <Handle type="source" position={Position.Bottom} className="!bg-cyan-500 !w-3 !h-3 !border-4 !border-[#050505]" />
        </div>
    );
}
