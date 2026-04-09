"use client";

import { Handle, Position } from "reactflow";
import { Slack } from "lucide-react";
import { motion } from "framer-motion";

export default function SlackNode({ data, selected }: any) {
    return (
        <div
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-purple-500/20 border-purple-500 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-purple-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-purple-50 border-b border-purple-100/50 flex items-center gap-2">
                <Slack size={14} className="text-purple-600" />
                <span className="text-[10px] font-black text-purple-700 uppercase tracking-widest">{data.label || "Slack Notification"}</span>
            </div>
            <div className="p-5 space-y-3">
                 <div className="flex items-center gap-2">
                    <span className="px-2 py-1 bg-purple-100/50 rounded-lg text-[9px] font-black text-purple-700 uppercase tracking-tighter">Channel</span>
                    <span className="text-xs font-black text-slate-700 uppercase tracking-tighter">{data.channel || "#leads"}</span>
                </div>
                <div className="w-full bg-slate-50 border border-slate-100 rounded-xl px-4 py-3 text-[10px] text-slate-400 font-bold italic line-clamp-2 shadow-inner">
                    "Incoming lead captured from chatbot session..."
                </div>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-4 !h-4 !bg-purple-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
        </div>
    );
}
