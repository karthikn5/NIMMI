"use client";

import { Handle, Position } from "reactflow";
import { Play } from "lucide-react";

interface StartNodeProps {
    data: { label: string };
    selected: boolean;
}

export default function StartNode({ data, selected }: StartNodeProps) {
    return (
        <div
            className={`w-64 px-6 py-4 rounded-xl bg-gradient-to-br from-green-500 to-green-600 text-white shadow-lg transition-all ${selected ? "ring-2 ring-white ring-offset-2 ring-offset-[#0a0a0a]" : ""
                }`}
        >
            <div className="flex items-center gap-2 font-bold">
                <Play size={16} fill="white" />
                {data.label}
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-3 !h-3 !bg-white !border-2 !border-green-600"
            />
        </div>
    );
}
