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
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-purple-500/20 border-purple-500 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-purple-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-purple-50 border-b border-purple-100/50 flex items-center gap-2">
                <GitBranch size={14} className="text-purple-600" />
                <span className="text-[10px] font-black text-purple-700 uppercase tracking-widest">{data.label}</span>
            </div>
            <div className="p-5 space-y-3">
                <div className="flex items-center gap-2">
                    <div className="px-2 py-1 bg-slate-100 rounded-lg text-[10px] font-mono font-bold text-slate-500 uppercase tracking-tighter">IF</div>
                    <span className="text-xs font-black text-slate-700 uppercase tracking-tighter">{data.variable || "variable"}</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="px-2 py-1 bg-slate-100 rounded-lg text-[10px] font-bold text-slate-500 uppercase tracking-tighter">{data.operator || "equals"}</div>
                    <span className="text-xs font-black text-slate-700">{data.value || "value"}</span>
                </div>
            </div>

            <div className="flex justify-between px-6 pb-2">
                <div className="relative flex flex-col items-center">
                    <Handle
                        type="source"
                        position={Position.Bottom}
                        id="true"
                        className="!left-auto !relative !translate-x-0 !w-4 !h-4 !bg-emerald-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
                    />
                    <span className="text-[9px] font-black text-emerald-600 uppercase tracking-widest mt-1">TRUE</span>
                </div>
                <div className="relative flex flex-col items-center">
                    <Handle
                        type="source"
                        position={Position.Bottom}
                        id="false"
                        className="!left-auto !relative !translate-x-0 !w-4 !h-4 !bg-rose-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
                    />
                    <span className="text-[9px] font-black text-rose-600 uppercase tracking-widest mt-1">FALSE</span>
                </div>
            </div>
        </div>
    );
}
