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
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-pink-500/20 border-pink-500 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-pink-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-pink-50 border-b border-pink-100/50 flex items-center gap-2">
                <ImageIcon size={14} className="text-pink-600" />
                <span className="text-[10px] font-black text-pink-700 uppercase tracking-widest">{data.label || "Display Image"}</span>
            </div>
            <div className="p-3">
                <div className="aspect-video bg-slate-100 rounded-xl overflow-hidden flex items-center justify-center border border-slate-200">
                    {data.url ? (
                        <img src={data.url} alt={data.label} className="w-full h-full object-cover" />
                    ) : (
                        <div className="flex flex-col items-center gap-2 text-slate-300">
                             <ImageIcon size={24} />
                             <span className="text-[10px] font-black uppercase tracking-tighter">No Media</span>
                        </div>
                    )}
                </div>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-4 !h-4 !bg-pink-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
        </div>
    );
}
