"use client";

import { Handle, Position } from "reactflow";
import { LayoutGrid } from "lucide-react";

interface MultipleChoiceNodeProps {
    data: {
        label: string;
        message?: string;
        options: string[];
        required?: boolean;
    };
    selected?: boolean;
}

/**
 * Each choice has its own connector on the right, so the flow can branch on the answer.
 * The connector at the bottom is used for any choice that isn't linked on its own.
 */
export default function MultipleChoiceNode({ data, selected }: MultipleChoiceNodeProps) {
    const options = (data.options || []).map((o) => String(o).trim()).filter(Boolean);
    const question = data.message?.trim() || (data.label && data.label !== "Multiple Choice" && data.label !== "Choices" ? data.label : "");
    return (
        <div className={`w-64 rounded-lg bg-white border border-line-strong shadow-[0_1px_3px_rgba(28,23,25,0.08)] ${selected ? "ring-2 ring-plum/20 border-plum" : ""}`}>
            <Handle type="target" position={Position.Top} className="!w-3 !h-3 !bg-stone-400 !border-2 !border-white" />
            <div className="px-4 py-3 bg-stone-50/70 border-b border-line rounded-t-lg flex items-center gap-2">
                <LayoutGrid size={14} className="text-amber-600" />
                <span className="text-[12px] font-medium text-ink">Choices {data.required && <span className="text-signal">*</span>}</span>
            </div>
            <div className="p-3 space-y-1.5">
                {question && <p className="text-[13px] text-stone-700 px-1 pb-1">{question}</p>}
                {options.map((option, i) => (
                    <div key={`${option}-${i}`} className="relative px-3 py-1.5 rounded-md border border-line text-[12px] text-stone-700 bg-white">
                        {option}
                        <Handle type="source" position={Position.Right} id={option}
                                className="!w-2.5 !h-2.5 !bg-amber-500 !border-2 !border-white !-right-[19px]" title={`If they choose “${option}”`} />
                    </div>
                ))}
                {!options.length && (
                    <div className="py-2 border border-dashed border-line-strong rounded-md text-[12px] text-stone-400 text-center">No choices yet</div>
                )}
            </div>
            <div className="relative pb-2 text-center text-[11px] text-stone-400">Any answer</div>
            <Handle type="source" position={Position.Bottom} className="!w-3 !h-3 !bg-stone-400 !border-2 !border-white" title="Any other answer" />
        </div>
    );
}
