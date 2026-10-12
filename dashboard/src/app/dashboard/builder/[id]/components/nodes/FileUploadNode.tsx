"use client";

import { Handle, Position } from "reactflow";
import { Upload } from "lucide-react";

interface FileUploadNodeProps {
    data: {
        label: string;
        required?: boolean;
    };
    selected?: boolean;
}

export default function FileUploadNode({ data, selected }: FileUploadNodeProps) {
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
                <Upload size={14} className="text-indigo-600" />
                <span className="text-[12px] font-medium text-ink">{data.label} {data.required && <span className="text-red-500">*</span>}</span>
            </div>
            <div className="p-5">
                <div className="w-full border-2 border-dashed border-slate-100 rounded-2xl p-4 flex flex-col items-center gap-2 bg-slate-50/50">
                    <Upload size={20} className="text-slate-300" />
                    <span className="text-[10px] font-medium text-slate-400">Upload Zone</span>
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
