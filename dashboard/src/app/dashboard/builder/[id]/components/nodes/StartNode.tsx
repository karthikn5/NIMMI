"use client";

import { Handle, Position } from "reactflow";
import { Play } from "lucide-react";

interface StartNodeProps {
    data: { label: string };
    selected: boolean;
}

export default function StartNode({ selected }: StartNodeProps) {
    return (
        <div className={`inline-flex items-center gap-2 pl-2 pr-4 h-10 rounded-full bg-white border shadow-[0_1px_3px_rgba(28,23,25,0.08)] ${selected ? "border-plum ring-2 ring-plum/20" : "border-line-strong"}`}>
            <span className="h-6 w-6 rounded-full bg-plum flex items-center justify-center">
                <Play size={11} fill="white" className="text-white ml-0.5" />
            </span>
            <span className="text-[13px] font-medium text-ink">Start</span>
            <Handle type="source" position={Position.Bottom} className="!w-3 !h-3 !bg-stone-400 !border-2 !border-white" />
        </div>
    );
}
