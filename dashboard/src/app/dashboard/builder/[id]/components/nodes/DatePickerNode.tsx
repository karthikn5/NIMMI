"use client";

import { Handle, Position } from "reactflow";
import { Calendar } from "lucide-react";

interface DatePickerNodeProps {
    data: {
        label: string;
        placeholder?: string;
        required?: boolean;
    };
    selected?: boolean;
}

export default function DatePickerNode({ data, selected }: DatePickerNodeProps) {
    return (
        <div
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-indigo-500/20 border-indigo-500 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-indigo-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-indigo-50 border-b border-indigo-100/50 flex items-center gap-2">
                <Calendar size={14} className="text-indigo-600" />
                <span className="text-[10px] font-black text-indigo-700 uppercase tracking-widest">{data.label} {data.required && <span className="text-red-500">*</span>}</span>
            </div>
            <div className="p-5">
                <div className="w-full bg-slate-50 border border-slate-100 rounded-xl px-4 py-3 text-xs text-slate-400 font-bold italic shadow-inner flex items-center justify-between">
                    <span>{data.placeholder || "Select date..."}</span>
                    <Calendar size={14} className="text-slate-300" />
                </div>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-4 !h-4 !bg-indigo-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
        </div>
    );
}
