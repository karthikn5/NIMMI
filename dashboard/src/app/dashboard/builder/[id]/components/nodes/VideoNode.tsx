"use client";

import { Handle, Position } from "reactflow";
import { Video } from "lucide-react";

export default function VideoNode({ data }: { data: any }) {
    return (
        <div className="w-64 bg-[#1a1a1a] border-2 border-red-500/50 rounded-2xl p-4 shadow-2xl">
            <div className="flex items-center gap-3 mb-3 pb-3 border-b border-white/5">
                <div className="w-8 h-8 bg-red-500/10 rounded-lg flex items-center justify-center">
                    <Video size={14} className="text-red-400" />
                </div>
                <span className="text-xs font-bold text-white/70 uppercase tracking-widest">{data.label || "Embed Video"}</span>
            </div>

            <div className="aspect-video bg-white/5 rounded-lg border border-white/10 flex flex-col items-center justify-center">
                <Video size={24} className="text-white/10 mb-2" />
                <p className="text-[9px] text-white/20 uppercase font-bold tracking-widest">Video URL Ready</p>
            </div>

            <Handle type="target" position={Position.Top} className="!bg-red-500 !w-3 !h-3 !border-4 !border-[#1a1a1a]" />
            <Handle type="source" position={Position.Bottom} className="!bg-red-500 !w-3 !h-3 !border-4 !border-[#1a1a1a]" />
        </div>
    );
}
