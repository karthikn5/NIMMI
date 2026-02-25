"use client";

import { Handle, Position } from "reactflow";
import { Image as ImageIcon } from "lucide-react";

export default function ImageNode({ data }: { data: any }) {
    return (
        <div className="w-64 bg-[#1a1a1a] border-2 border-pink-500/50 rounded-2xl p-4 shadow-2xl">
            <div className="flex items-center gap-3 mb-3 pb-3 border-b border-white/5">
                <div className="w-8 h-8 bg-pink-500/10 rounded-lg flex items-center justify-center">
                    <ImageIcon size={14} className="text-pink-400" />
                </div>
                <span className="text-xs font-bold text-white/70 uppercase tracking-widest">{data.label || "Display Image"}</span>
            </div>

            <div className="aspect-video bg-white/5 rounded-lg border border-white/10 flex items-center justify-center overflow-hidden">
                {data.imageUrl ? (
                    <img src={data.imageUrl} className="w-full h-full object-cover" alt="Preview" />
                ) : (
                    <ImageIcon size={24} className="text-white/10" />
                )}
            </div>

            <Handle type="target" position={Position.Top} className="!bg-pink-500 !w-3 !h-3 !border-4 !border-[#1a1a1a]" />
            <Handle type="source" position={Position.Bottom} className="!bg-pink-500 !w-3 !h-3 !border-4 !border-[#1a1a1a]" />
        </div>
    );
}
