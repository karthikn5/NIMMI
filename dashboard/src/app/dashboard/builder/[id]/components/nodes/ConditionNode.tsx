"use client";

import { Handle, Position } from "reactflow";
import { GitBranch } from "lucide-react";

interface ConditionNodeProps {
    data: {
        label: string;
        variable: string;
        operator: "equals" | "contains" | "greater_than" | "less_than";
        value: string;
    };
    selected: boolean;
}

export default function ConditionNode({ data, selected }: ConditionNodeProps) {
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
                <GitBranch size={14} className="text-plum" />
                <span className="text-[12px] font-medium text-ink">{data.label}</span>
            </div>
            <div className="p-5 space-y-3">
                <div className="flex items-center gap-2">
                    <div className="px-2 py-1 bg-slate-100 rounded-lg text-[10px] font-mono font-normal text-slate-500">IF</div>
                    <span className="text-xs font-medium text-slate-700">{data.variable || "variable"}</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="px-2 py-1 bg-slate-100 rounded-lg text-[10px] font-normal text-slate-500">{data.operator || "equals"}</div>
                    <span className="text-xs font-medium text-slate-700">{data.value || "value"}</span>
                </div>
            </div>

            <div className="flex justify-between px-6 pb-2">
                <div className="relative flex flex-col items-center">
                    <Handle
                        type="source"
                        position={Position.Bottom}
                        id="true"
                        className="!left-auto !relative !translate-x-0 !w-3 !h-3 !bg-emerald-500 !border-2 !border-white !shadow-sm transition-transform hover:scale-125"
                    />
                    <span className="text-[9px] font-medium text-emerald-600 mt-1">TRUE</span>
                </div>
                <div className="relative flex flex-col items-center">
                    <Handle
                        type="source"
                        position={Position.Bottom}
                        id="false"
                        className="!left-auto !relative !translate-x-0 !w-3 !h-3 !bg-rose-500 !border-2 !border-white !shadow-sm transition-transform hover:scale-125"
                    />
                    <span className="text-[9px] font-medium text-rose-600 mt-1">FALSE</span>
                </div>
            </div>
        </div>
    );
}
