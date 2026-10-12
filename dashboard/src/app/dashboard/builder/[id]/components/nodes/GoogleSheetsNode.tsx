"use client";

import { Handle, Position } from "reactflow";
import { Table } from "lucide-react";
import { motion } from "framer-motion";

export default function GoogleSheetsNode({ data, selected }: any) {
    return (
        <div
            className={`w-64 rounded-lg bg-white border border-line-strong overflow-hidden shadow-[0_1px_3px_rgba(28,23,25,0.08)] transition-all ${selected ? "ring-2 ring-plum/20 border-plum" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-3 !h-3 !bg-emerald-500 !border-2 !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-stone-50/70 border-b border-line flex items-center gap-2">
                <Table size={14} className="text-emerald-600" />
                <span className="text-[12px] font-medium text-ink">{data.label || "Sheets Export"}</span>
            </div>
            <div className="p-5 space-y-3">
                 <div className="flex items-center gap-2">
                    <span className="px-2 py-1 bg-emerald-100/50 rounded-lg text-[9px] font-medium text-emerald-700">Sheet</span>
                    <span className="text-xs font-medium text-slate-700">{data.sheetName || "Sheet1"}</span>
                </div>
                <div className="w-full bg-slate-50 border border-slate-100 rounded-xl px-4 py-3 text-[10px] text-slate-400 font-mono font-normal truncate shadow-inner">
                    {data.spreadsheetId || "Spreadsheet ID..."}
                </div>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-3 !h-3 !bg-emerald-500 !border-2 !border-white !shadow-sm transition-transform hover:scale-125"
            />
        </div>
    );
}
