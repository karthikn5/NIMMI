"use client";

import { Handle, Position } from "reactflow";
import { LayoutGrid } from "lucide-react";

interface MultipleChoiceNodeProps {
    data: {
        label: string;
        options: string[];
        required?: boolean;
    };
    selected?: boolean;
}

export default function MultipleChoiceNode({ data, selected }: MultipleChoiceNodeProps) {
    return (
        <div
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-amber-500/20 border-amber-500 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-amber-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-amber-50 border-b border-amber-100/50 flex items-center gap-2">
                <LayoutGrid size={14} className="text-amber-600" />
                <span className="text-[10px] font-black text-amber-700 uppercase tracking-widest">{data.label} {data.required && <span className="text-red-500">*</span>}</span>
            </div>
            <div className="p-5 space-y-2">
                {(data.options || []).slice(0, 3).map((option: string, i: number) => (
                    <div key={i} className="px-4 py-2 bg-slate-50 border border-slate-100 rounded-xl text-xs font-bold text-slate-600 shadow-sm flex items-center gap-2">
                        <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                        {option}
                    </div>
                ))}
                {(data.options || []).length > 3 && (
                    <div className="text-[10px] text-slate-400 font-bold uppercase tracking-tighter text-center pt-1">
                        + {(data.options || []).length - 3} more options
                    </div>
                )}
                {(data.options || []).length === 0 && (
                    <div className="py-2 border border-dashed border-slate-200 rounded-xl text-[10px] text-slate-300 font-bold uppercase tracking-widest text-center">
                        No options set
                    </div>
                )}
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-4 !h-4 !bg-amber-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
        </div>
    );
}
