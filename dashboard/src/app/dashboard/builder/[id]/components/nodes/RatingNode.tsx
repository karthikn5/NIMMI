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
            className={`w-64 rounded-lg bg-white border border-line-strong overflow-hidden shadow-[0_1px_3px_rgba(28,23,25,0.08)] transition-all ${selected ? "ring-2 ring-plum/20 border-plum" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-3 !h-3 !bg-stone-400 !border-2 !border-white transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-stone-50/70 border-b border-line flex items-center gap-2">
                <Star size={14} className="text-yellow-600 font-normal" />
                <span className="text-[12px] font-medium text-ink">{data.label} {data.required && <span className="text-red-500">*</span>}</span>
            </div>
            <div className="p-5 flex justify-center gap-2">
                {[1, 2, 3, 4, 5].map((i) => (
                    <Star key={i} size={18} className="text-yellow-400 fill-yellow-200/50" />
                ))}
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-3 !h-3 !bg-stone-400 !border-2 !border-white transition-transform hover:scale-125"
            />
        </div>
    );
}
