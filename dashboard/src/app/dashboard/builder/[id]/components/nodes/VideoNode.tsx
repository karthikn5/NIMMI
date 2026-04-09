"use client";

import { Handle, Position } from "reactflow";
import { Video as VideoIcon, Play } from "lucide-react";

interface VideoNodeProps {
    data: {
        label: string;
        url?: string;
    };
    selected?: boolean;
}

export default function VideoNode({ data, selected }: VideoNodeProps) {
    return (
        <div
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-red-500/20 border-red-500 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-red-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-red-50 border-b border-red-100/50 flex items-center gap-2">
                <VideoIcon size={14} className="text-red-600" />
                <span className="text-[10px] font-black text-red-700 uppercase tracking-widest">{data.label || "Display Video"}</span>
            </div>
            <div className="p-3">
                <div className="aspect-video bg-slate-100 rounded-xl overflow-hidden flex items-center justify-center border border-slate-200 relative group">
                    {data.url ? (
                        <div className="w-full h-full bg-slate-900 flex items-center justify-center">
                             <Play size={24} className="text-white" fill="white" />
                        </div>
                    ) : (
                        <div className="flex flex-col items-center gap-2 text-slate-300">
                             <VideoIcon size={24} />
                             <span className="text-[10px] font-black uppercase tracking-tighter">No Video Source</span>
                        </div>
                    )}
                </div>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-4 !h-4 !bg-red-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
        </div>
    );
}
