"use client";

import { Handle, Position } from "reactflow";
import { Upload } from "lucide-react";

export default function FileUploadNode({ data }: { data: any }) {
    return (
        <div className="w-64 bg-[#1a1a1a] border-2 border-indigo-500/50 rounded-2xl p-4 shadow-2xl">
            <div className="flex items-center gap-3 mb-3 pb-3 border-b border-white/5">
                <div className="w-8 h-8 bg-indigo-500/10 rounded-lg flex items-center justify-center">
                    <Upload size={14} className="text-indigo-400" />
                </div>
                <span className="text-xs font-bold text-white/70 uppercase tracking-widest">{data.label || "File Upload"}</span>
            </div>

            <div className="border border-dashed border-white/10 rounded-lg p-3 text-center bg-white/5">
                <p className="text-[10px] text-white/40">{data.placeholder || "Click to upload files"}</p>
                <div className="mt-2 flex justify-center gap-1">
                    <div className="w-3 h-1 bg-white/10 rounded-full" />
                    <div className="w-6 h-1 bg-indigo-500/40 rounded-full" />
                </div>
            </div>

            <Handle type="target" position={Position.Top} className="!bg-indigo-500 !w-3 !h-3 !border-4 !border-[#1a1a1a]" />
            <Handle type="source" position={Position.Bottom} className="!bg-indigo-500 !w-3 !h-3 !border-4 !border-[#1a1a1a]" />
        </div>
    );
}
