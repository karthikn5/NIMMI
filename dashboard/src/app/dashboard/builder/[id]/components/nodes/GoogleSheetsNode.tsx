"use client";

import { Handle, Position } from "reactflow";
import { Table } from "lucide-react";
import { motion } from "framer-motion";

const GoogleSheetsNode = ({ data, selected }: any) => {
    return (
        <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className={`px-4 py-3 rounded-2xl bg-zinc-900 border-2 transition-all ${selected ? "border-green-500 shadow-[0_0_20px_rgba(34,197,94,0.2)]" : "border-white/10"
                } min-w-[180px] shadow-2xl relative overflow-hidden group`}
        >
            <div className="absolute top-0 left-0 w-1 h-full bg-green-500" />

            <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-green-500/20 rounded-xl flex items-center justify-center border border-green-500/20 group-hover:scale-110 transition-transform">
                    <Table size={20} className="text-green-400" />
                </div>
                <div>
                    <p className="text-[10px] font-bold text-white/40 uppercase tracking-widest">{data.label || "Sheets Sync"}</p>
                    <p className="text-xs font-bold text-white/90 truncate max-w-[100px]">
                        {data.spreadsheetName || "Choose Sheet"}
                    </p>
                </div>
            </div>

            <Handle type="target" position={Position.Left} className="w-3 h-3 bg-green-500 border-2 border-zinc-900" />
            <Handle type="source" position={Position.Right} className="w-3 h-3 bg-green-500 border-2 border-zinc-900" />
        </motion.div>
    );
};

export default GoogleSheetsNode;
