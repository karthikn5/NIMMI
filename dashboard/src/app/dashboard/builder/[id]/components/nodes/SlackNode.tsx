"use client";

import { Handle, Position } from "reactflow";
import { Slack } from "lucide-react";
import { motion } from "framer-motion";

export default function SlackNode({ data, selected }: any) {
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
                <Slack size={14} className="text-plum" />
                <span className="text-[12px] font-medium text-ink">{data.label || "Slack Notification"}</span>
            </div>
            <div className="p-5 space-y-3">
                 <div className="flex items-center gap-2">
                    <span className="px-2 py-1 bg-plum-tint/50 rounded-lg text-[9px] font-medium text-plum-hover">Channel</span>
                    <span className="text-xs font-medium text-slate-700">{data.channel || "#leads"}</span>
                </div>
                <div className="w-full bg-slate-50 border border-slate-100 rounded-xl px-4 py-3 text-[10px] text-slate-400 font-normal italic line-clamp-2 shadow-inner">
                    "Incoming lead captured from chatbot session..."
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
