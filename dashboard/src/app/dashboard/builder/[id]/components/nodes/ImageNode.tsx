"use client";

import { Handle, Position } from "reactflow";
import { Image as ImageIcon } from "lucide-react";

interface ImageNodeProps {
    data: {
        label: string;
        url?: string;
    };
    selected?: boolean;
}

export default function ImageNode({ data, selected }: ImageNodeProps) {
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
                <ImageIcon size={14} className="text-pink-600" />
                <span className="text-[12px] font-medium text-ink">{data.label || "Display Image"}</span>
            </div>
            <div className="p-3">
                <div className="aspect-video bg-slate-100 rounded-xl overflow-hidden flex items-center justify-center border border-line-strong">
                    {data.url ? (
                        <img src={data.url} alt={data.label} className="w-full h-full object-cover" />
                    ) : (
                        <div className="flex flex-col items-center gap-2 text-slate-300">
                             <ImageIcon size={24} />
                             <span className="text-[10px] font-medium">No Media</span>
                        </div>
                    )}
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
