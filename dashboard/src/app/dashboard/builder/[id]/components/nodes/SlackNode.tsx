"use client";

import { Handle, Position } from "reactflow";
import { Slack } from "lucide-react";
import { motion } from "framer-motion";

const SlackNode = ({ data, selected }: any) => {
    return (
        <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className={`px-4 py-3 rounded-2xl bg-zinc-900 border-2 transition-all ${selected ? "border-purple-500 shadow-[0_0_20px_rgba(168,85,247,0.2)]" : "border-white/10"
                } min-w-[180px] shadow-2xl relative overflow-hidden group`}
        >
            <div className="absolute top-0 left-0 w-1 h-full bg-purple-500" />

            <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-purple-500/20 rounded-xl flex items-center justify-center border border-purple-500/20 group-hover:scale-110 transition-transform">
                    <Slack size={20} className="text-purple-400" />
                </div>
                <div>
                    <p className="text-[10px] font-bold text-white/40 uppercase tracking-widest">{data.label || "Slack Notify"}</p>
                    <p className="text-xs font-bold text-white/90 truncate max-w-[100px]">
                        {data.channel || "Choose Channel"}
                    </p>
                </div>
            </div>

            <Handle type="target" position={Position.Left} className="w-3 h-3 bg-purple-500 border-2 border-zinc-900" />
            <Handle type="source" position={Position.Right} className="w-3 h-3 bg-purple-500 border-2 border-zinc-900" />
        </motion.div>
    );
};

export default SlackNode;
