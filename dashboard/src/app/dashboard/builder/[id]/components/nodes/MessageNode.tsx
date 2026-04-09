"use client";

import { Handle, Position } from "reactflow";
import { MessageSquare } from "lucide-react";

interface MessageNodeProps {
    data: { label: string; message: string };
    selected: boolean;
}

export default function MessageNode({ data, selected }: MessageNodeProps) {
    return (
        <div
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-blue-500/20 border-blue-500 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-blue-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-blue-50 border-b border-blue-100/50 flex items-center gap-2">
                <MessageSquare size={14} className="text-blue-600" />
                <span className="text-[10px] font-black text-blue-700 uppercase tracking-widest">{data.label}</span>
            </div>
            <div className="p-5">
                <p className="text-sm font-bold text-slate-700 leading-relaxed line-clamp-3 italic opacity-80">"{data.message}"</p>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-4 !h-4 !bg-blue-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
        </div>
    );
}
