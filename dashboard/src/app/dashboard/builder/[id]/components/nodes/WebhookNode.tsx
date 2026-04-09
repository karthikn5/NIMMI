"use client";

import { Handle, Position } from "reactflow";
import { Link2 as WebhookLucide } from "lucide-react";

interface WebhookNodeProps {
    data: {
        label?: string;
        url?: string;
    };
    selected?: boolean;
}

export default function WebhookNode({ data, selected }: WebhookNodeProps) {
    return (
        <div
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-orange-500/20 border-orange-500 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-orange-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-orange-50 border-b border-orange-100/50 flex items-center gap-2">
                <WebhookLucide size={14} className="text-orange-600" />
                <span className="text-[10px] font-black text-orange-700 uppercase tracking-widest">{data.label || "Webhook Relay"}</span>
            </div>
            <div className="p-5">
                 <div className="flex items-center gap-2 mb-2">
                    <div className="w-2 h-2 rounded-full bg-orange-500 animate-pulse shadow-[0_0_8px_rgba(249,115,22,0.5)]" />
                    <span className="text-[10px] font-black text-orange-600 uppercase tracking-widest">Active Relay</span>
                </div>
                <div className="w-full bg-slate-50 border border-slate-100 rounded-xl px-4 py-3 text-xs text-slate-400 font-mono font-bold truncate shadow-inner">
                    {data.url || "Waiting for integration URL..."}
                </div>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-4 !h-4 !bg-orange-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
        </div>
    );
}
