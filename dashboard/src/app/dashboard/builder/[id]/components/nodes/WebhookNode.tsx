"use client";

import { Handle, Position } from "reactflow";
import { Link2 } from "lucide-react";

export default function WebhookNode({ data }: { data: any }) {
    return (
        <div className="w-64 bg-[#050505] border-2 border-orange-500/50 rounded-2xl p-4 shadow-2xl overflow-hidden relative group">
            <div className="absolute top-0 right-0 w-24 h-24 bg-orange-500/5 blur-2xl rounded-full -mr-12 -mt-12" />

            <div className="flex items-center gap-3 mb-3 pb-3 border-b border-white/10 relative">
                <div className="w-8 h-8 bg-orange-500/10 rounded-lg flex items-center justify-center">
                    <Link2 size={14} className="text-orange-400" />
                </div>
                <span className="text-xs font-bold text-white uppercase tracking-widest">{data.label || "External Webhook"}</span>
            </div>

            <div className="space-y-2 relative">
                <div className="px-3 py-1.5 bg-white/5 rounded-md border border-white/5">
                    <div className="flex items-center gap-2 mb-1">
                        <span className="text-[8px] font-bold text-orange-400 uppercase tracking-widest">URL</span>
                    </div>
                    <span className="text-[9px] text-white/40 truncate block">
                        {data.url || "https://hooks.zapier.com/..."}
                    </span>
                </div>
                <p className="text-[9px] text-white/20 px-1 italic">Triggers external automation (Zapier/Make)</p>
            </div>

            <Handle type="target" position={Position.Top} className="!bg-orange-500 !w-3 !h-3 !border-4 !border-[#050505]" />
            <Handle type="source" position={Position.Bottom} className="!bg-orange-500 !w-3 !h-3 !border-4 !border-[#050505]" />
        </div>
    );
}
