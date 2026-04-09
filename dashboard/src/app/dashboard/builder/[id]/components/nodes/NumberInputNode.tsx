 "use client";

import { Handle, Position } from "reactflow";
import { Hash } from "lucide-react";

interface NumberInputNodeProps {
    data: { label: string; placeholder: string; required: boolean };
    selected: boolean;
}

export default function NumberInputNode({ data, selected }: NumberInputNodeProps) {
    return (
        <div
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-orange-500/20 border-orange-500 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-orange-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-orange-50 border-b border-orange-100/50 flex items-center gap-2">
                <Hash size={14} className="text-orange-600" />
                <span className="text-[10px] font-black text-orange-700 uppercase tracking-widest">{data.label} {data.required && <span className="text-red-500">*</span>}</span>
            </div>
            <div className="p-5">
                <div className="w-full bg-slate-50 border border-slate-100 rounded-xl px-4 py-3 text-xs text-slate-400 font-bold italic shadow-inner">
                    {data.placeholder || "0"}
                </div>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-4 !h-4 !bg-orange-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
        </div>
    );
}
