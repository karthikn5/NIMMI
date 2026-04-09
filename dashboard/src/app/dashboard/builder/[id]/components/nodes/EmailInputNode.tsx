"use client";

import { Handle, Position } from "reactflow";
import { Mail } from "lucide-react";

interface EmailInputNodeProps {
    data: { label: string; placeholder: string; required: boolean };
    selected: boolean;
}

export default function EmailInputNode({ data, selected }: EmailInputNodeProps) {
    return (
        <div
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-cyan-500/20 border-cyan-500 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-cyan-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-cyan-50 border-b border-cyan-100/50 flex items-center gap-2">
                <Mail size={14} className="text-cyan-600" />
                <span className="text-[10px] font-black text-cyan-700 uppercase tracking-widest">{data.label} {data.required && <span className="text-red-500">*</span>}</span>
            </div>
            <div className="p-5">
                <div className="w-full bg-slate-50 border border-slate-100 rounded-xl px-4 py-3 text-xs text-slate-400 font-bold italic shadow-inner">
                    {data.placeholder || "email@example.com"}
                </div>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-4 !h-4 !bg-cyan-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
        </div>
    );
}
