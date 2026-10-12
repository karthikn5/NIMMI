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
            className={`w-64 rounded-lg bg-white border border-line-strong overflow-hidden shadow-[0_1px_3px_rgba(28,23,25,0.08)] transition-all ${selected ? "ring-2 ring-plum/20 border-plum" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-3 !h-3 !bg-stone-400 !border-2 !border-white transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-stone-50/70 border-b border-line flex items-center gap-2">
                <Variable size={14} className="text-blue-600" />
                <span className="text-[12px] font-medium text-ink">{data.label || "Variable Set"}</span>
            </div>
            <div className="p-5 space-y-3">
                 <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2">
                    <span className="text-[10px] font-medium text-slate-400">Set</span>
                    <span className="text-xs font-mono font-medium text-blue-700">{data.variableName || "unnamed"}</span>
                </div>
                <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] font-medium text-slate-400">to</span>
                    <span className="text-xs font-medium text-slate-700 truncate">{data.variableValue || "undefined"}</span>
                </div>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-3 !h-3 !bg-stone-400 !border-2 !border-white transition-transform hover:scale-125"
            />
        </div>
    );
}
