"use client";

import { Handle, Position } from "reactflow";
import { Star } from "lucide-react";

export default function RatingNode({ data }: { data: any }) {
    return (
        <div className="w-64 bg-[#1a1a1a] border-2 border-amber-500/50 rounded-2xl p-4 shadow-2xl">
            <div className="flex items-center gap-3 mb-3 pb-3 border-b border-white/5">
                <div className="w-8 h-8 bg-amber-500/10 rounded-lg flex items-center justify-center">
                    <Star size={14} className="text-amber-400" />
                </div>
                <span className="text-xs font-bold text-white/70 uppercase tracking-widest">{data.label || "Rating"}</span>
            </div>

            <div className="flex justify-center gap-2">
                {[1, 2, 3, 4, 5].map(i => (
                    <Star key={i} size={16} className="text-amber-400/30" />
                ))}
            </div>
            <p className="text-[10px] text-white/30 text-center mt-3 uppercase font-bold tracking-widest">Scale: 1-5</p>

            <Handle type="target" position={Position.Top} className="!bg-amber-500 !w-3 !h-3 !border-4 !border-[#1a1a1a]" />
            <Handle type="source" position={Position.Bottom} className="!bg-amber-500 !w-3 !h-3 !border-4 !border-[#1a1a1a]" />
        </div>
    );
}
