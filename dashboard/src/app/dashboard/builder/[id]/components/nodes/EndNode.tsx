"use client";

import { Handle, Position } from "reactflow";
import { Square } from "lucide-react";

interface EndNodeProps {
    data: { label: string; message: string };
    selected: boolean;
}

export default function EndNode({ data, selected }: EndNodeProps) {
    return (
        <div
            className={`w-64 px-6 py-4 rounded-xl bg-gradient-to-br from-red-500 to-red-600 text-white shadow-lg transition-all ${selected ? "ring-2 ring-white ring-offset-2 ring-offset-[#0a0a0a]" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-3 !h-3 !bg-white !border-2 !border-red-600"
            />
            <div className="flex items-center gap-2 font-bold">
                <Square size={14} fill="white" />
                {data.label}
            </div>
            <p className="text-xs text-white/70 mt-1 max-w-[150px]">{data.message}</p>
        </div>
    );
}
