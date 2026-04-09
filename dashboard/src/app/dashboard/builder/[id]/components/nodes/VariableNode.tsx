"use client";

import { Handle, Position } from "reactflow";
import { Variable } from "lucide-react";

interface VariableNodeProps {
    data: {
        label?: string;
        variableName?: string;
        variableValue?: string;
    };
    selected?: boolean;
}

export default function VariableNode({ data, selected }: VariableNodeProps) {
    return (
        <div
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-blue-500/20 border-blue-500 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-blue-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-blue-50 border-b border-blue-100/50 flex items-center gap-2">
                <Variable size={14} className="text-blue-600" />
                <span className="text-[10px] font-black text-blue-700 uppercase tracking-widest">{data.label || "Variable Set"}</span>
            </div>
            <div className="p-5 space-y-3">
                 <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2">
                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-tighter">Set</span>
                    <span className="text-xs font-mono font-black text-blue-700 uppercase tracking-tighter">{data.variableName || "unnamed"}</span>
                </div>
                <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-tighter">to</span>
                    <span className="text-xs font-black text-slate-700 truncate">{data.variableValue || "undefined"}</span>
                </div>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-4 !h-4 !bg-blue-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
        </div>
    );
}
