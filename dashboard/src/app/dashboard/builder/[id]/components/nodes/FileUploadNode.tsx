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
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-indigo-500/20 border-indigo-500 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-indigo-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-indigo-50 border-b border-indigo-100/50 flex items-center gap-2">
                <Upload size={14} className="text-indigo-600" />
                <span className="text-[10px] font-black text-indigo-700 uppercase tracking-widest">{data.label} {data.required && <span className="text-red-500">*</span>}</span>
            </div>
            <div className="p-5">
                <div className="w-full border-2 border-dashed border-slate-100 rounded-2xl p-4 flex flex-col items-center gap-2 bg-slate-50/50">
                    <Upload size={20} className="text-slate-300" />
                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-tighter">Upload Zone</span>
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
