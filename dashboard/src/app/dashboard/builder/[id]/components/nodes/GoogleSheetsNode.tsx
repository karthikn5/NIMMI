"use client";

import { Handle, Position } from "reactflow";
import { Table } from "lucide-react";
import { motion } from "framer-motion";

export default function GoogleSheetsNode({ data, selected }: any) {
    return (
        <div
            className={`w-64 rounded-[24px] bg-white border border-slate-200 overflow-hidden shadow-xl transition-all ${selected ? "ring-4 ring-emerald-500/20 border-emerald-500 scale-105" : ""
                }`}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-4 !h-4 !bg-emerald-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
            <div className="px-4 py-3 bg-emerald-50 border-b border-emerald-100/50 flex items-center gap-2">
                <Table size={14} className="text-emerald-600" />
                <span className="text-[10px] font-black text-emerald-700 uppercase tracking-widest">{data.label || "Sheets Export"}</span>
            </div>
            <div className="p-5 space-y-3">
                 <div className="flex items-center gap-2">
                    <span className="px-2 py-1 bg-emerald-100/50 rounded-lg text-[9px] font-black text-emerald-700 uppercase tracking-tighter">Sheet</span>
                    <span className="text-xs font-black text-slate-700 uppercase tracking-tighter">{data.sheetName || "Sheet1"}</span>
                </div>
                <div className="w-full bg-slate-50 border border-slate-100 rounded-xl px-4 py-3 text-[10px] text-slate-400 font-mono font-bold truncate shadow-inner">
                    {data.spreadsheetId || "Spreadsheet ID..."}
                </div>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-4 !h-4 !bg-emerald-500 !border-[3px] !border-white !shadow-sm transition-transform hover:scale-125"
            />
        </div>
    );
}
