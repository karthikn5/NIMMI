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
            className={`w-64 rounded-lg bg-white border border-line-strong overflow-hidden shadow-[0_1px_3px_rgba(28,23,25,0.08)] transition-all ${selected ? "ring-2 ring-plum/20 border-plum" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-3 !h-3 !bg-stone-400 !border-2 !border-white transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-stone-50/70 border-b border-line flex items-center gap-2">
                <WebhookLucide size={14} className="text-orange-600" />
                <span className="text-[12px] font-medium text-ink">{data.label || "Webhook Relay"}</span>
            </div>
            <div className="p-5">
                 <div className="flex items-center gap-2 mb-2">
                    <div className="w-2 h-2 rounded-full bg-orange-500 animate-pulse shadow-[0_0_8px_rgba(249,115,22,0.5)]" />
                    <span className="text-[12px] font-medium text-ink">Active Relay</span>
                </div>
                <div className="w-full bg-slate-50 border border-slate-100 rounded-xl px-4 py-3 text-xs text-slate-400 font-mono font-normal truncate shadow-inner">
                    {data.url || "Waiting for integration URL..."}
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
