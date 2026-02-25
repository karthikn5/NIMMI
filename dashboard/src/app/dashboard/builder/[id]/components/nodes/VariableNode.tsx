"use client";

import { Handle, Position } from "reactflow";
import { Variable } from "lucide-react";

export default function VariableNode({ data }: { data: any }) {
    return (
        <div className="w-64 bg-[#1a1a1a] border-2 border-blue-500/50 rounded-2xl p-4 shadow-2xl">
            <div className="flex items-center gap-3 mb-3 pb-3 border-b border-white/5">
                <div className="w-8 h-8 bg-blue-500/10 rounded-lg flex items-center justify-center">
                    <Variable size={14} className="text-blue-400" />
                </div>
                <span className="text-xs font-bold text-white/70 uppercase tracking-widest">{data.label || "Set Variable"}</span>
            </div>

            <div className="bg-blue-500/5 border border-blue-500/10 rounded-lg p-2 flex items-center justify-between">
                <span className="text-[10px] text-blue-400 font-mono italic">{data.variableName || "user_intent"}</span>
                <span className="text-[10px] text-white/40">=</span>
                <span className="text-[10px] text-white font-bold">{data.variableValue || "none"}</span>
            </div>

            <Handle type="target" position={Position.Top} className="!bg-blue-500 !w-3 !h-3 !border-4 !border-[#1a1a1a]" />
            <Handle type="source" position={Position.Bottom} className="!bg-blue-500 !w-3 !h-3 !border-4 !border-[#1a1a1a]" />
        </div>
    );
}
