"use client";

import { Handle, Position } from "reactflow";
import { Star } from "lucide-react";

interface RatingNodeProps {
    data: {
        label: string;
        required?: boolean;
    };
    selected?: boolean;
}

export default function RatingNode({ data, selected }: RatingNodeProps) {
    return (
        <div
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-yellow-500/20 border-yellow-500 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-yellow-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-yellow-50 border-b border-yellow-100/50 flex items-center gap-2">
                <Star size={14} className="text-yellow-600 font-bold" />
                <span className="text-[10px] font-black text-yellow-700 uppercase tracking-widest">{data.label} {data.required && <span className="text-red-500">*</span>}</span>
            </div>
            <div className="p-5 flex justify-center gap-2">
                {[1, 2, 3, 4, 5].map((i) => (
                    <Star key={i} size={18} className="text-yellow-400 fill-yellow-200/50" />
                ))}
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-4 !h-4 !bg-yellow-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
        </div>
    );
}
