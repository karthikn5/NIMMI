"use client";

import { useState, DragEvent } from "react";
import {
    Play, MessageSquare, Type, Mail, List, Calendar, Square,
    GripVertical, GitBranch, Hash, Image as ImageIcon, Video,
    Upload, Star, Clock, Variable, Globe, Sparkles, Phone, Link2, Slack, Table,
    MousePointer2, ChevronDown, Search
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

const categories = [
    {
        id: "basic",
        label: "Basic Elements",
        elements: [
            { type: "message", label: "Message", description: "Display bot message", icon: MessageSquare, color: "blue" },
            { type: "textInput", label: "Text Input", description: "Collect text response", icon: Type, color: "purple" },
            { type: "emailInput", label: "Email Input", description: "Validate email address", icon: Mail, color: "cyan" },
            { type: "numberInput", label: "Number", description: "Numerical response", icon: Hash, color: "orange" },
            { type: "phoneInput", label: "Phone", description: "Phone number input", icon: Phone, color: "green" },
            { type: "multipleChoice", label: "Multiple Choice", description: "Option buttons/radio", icon: List, color: "amber" },
        ]
    },
    {
        id: "media",
        label: "Media & Interactive",
        elements: [
            { type: "image", label: "Image", description: "Send an image", icon: ImageIcon, color: "pink" },
            { type: "video", label: "Video", description: "Embed a video", icon: Video, color: "red" },
            { type: "fileUpload", label: "File Upload", description: "Ask to upload files", icon: Upload, color: "indigo" },
            { type: "rating", label: "Rating", description: "Star/Emoji feedback", icon: Star, color: "amber" },
        ]
    },
    {
        id: "logic",
        label: "Logic & Flow",
        elements: [
            { type: "condition", label: "If Condition", description: "Branch based on input", icon: GitBranch, color: "purple" },
            { type: "delay", label: "Delay", description: "Wait for X seconds", icon: Clock, color: "white" },
            { type: "variable", label: "Set Variable", description: "Store data locally", icon: Variable, color: "blue" },
            { type: "end", label: "End Flow", description: "Terminate conversation", icon: Square, color: "red" },
        ]
    },
    {
        id: "advanced",
        label: "Integrations & AI",
        elements: [
            { type: "aiPrompt", label: "AI Prompt", description: "Custom AI reasoning step", icon: Sparkles, color: "cyan" },
            { type: "httpRequest", label: "HTTP Request", description: "Fetch external data", icon: Globe, color: "green" },
            { type: "webhook", label: "Webhook", description: "Trigger Zapier/Make", icon: Link2, color: "orange" },
            { type: "slack", label: "Slack", description: "Send Slack alert", icon: Slack, color: "purple" },
            { type: "googleSheets", label: "G-Sheets", description: "Sync to spreadsheet", icon: Table, color: "green" },
        ]
    }
];

const colorClasses: Record<string, { bg: string; text: string; border: string; iconBg: string }> = {
    green: { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-100", iconBg: "bg-emerald-100" },
    blue: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-100", iconBg: "bg-blue-100" },
    purple: { bg: "bg-purple-50", text: "text-purple-700", border: "border-purple-100", iconBg: "bg-purple-100" },
    cyan: { bg: "bg-cyan-50", text: "text-cyan-700", border: "border-cyan-100", iconBg: "bg-cyan-100" },
    amber: { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-100", iconBg: "bg-amber-100" },
    pink: { bg: "bg-pink-50", text: "text-pink-700", border: "border-pink-100", iconBg: "bg-pink-100" },
    red: { bg: "bg-rose-50", text: "text-rose-700", border: "border-rose-100", iconBg: "bg-rose-100" },
    orange: { bg: "bg-orange-50", text: "text-orange-700", border: "border-orange-100", iconBg: "bg-orange-100" },
    white: { bg: "bg-slate-50", text: "text-slate-700", border: "border-slate-200", iconBg: "bg-slate-100" },
    indigo: { bg: "bg-indigo-50", text: "text-indigo-700", border: "border-indigo-100", iconBg: "bg-indigo-100" },
};

export default function ElementsSidebar() {
    const [searchQuery, setSearchQuery] = useState("");
    const [expandedCategories, setExpandedCategories] = useState<string[]>(["basic", "media", "logic", "advanced"]);

    const onDragStart = (event: DragEvent, nodeType: string) => {
        event.dataTransfer.setData("application/reactflow", nodeType);
        event.dataTransfer.effectAllowed = "move";
    };

    const toggleCategory = (id: string) => {
        setExpandedCategories(prev =>
            prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id]
        );
    };

    const filteredCategories = categories.map(cat => ({
        ...cat,
        elements: cat.elements.filter(el =>
            el.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
            el.description.toLowerCase().includes(searchQuery.toLowerCase())
        )
    })).filter(cat => cat.elements.length > 0);

    return (
        <div className="space-y-6">
            {/* Search Bar */}
            <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                    type="text"
                    placeholder="Search elements..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-9 pr-4 py-2 text-xs outline-none focus:border-blue-500 transition-colors text-slate-900 placeholder:text-slate-400"
                />
            </div>

            <div className="space-y-4">
                {/* Start Node Indicator */}
                {/* Start Node Indicator */}
                <div className="flex items-center gap-4 p-4 rounded-2xl bg-emerald-50 border border-emerald-100 opacity-60 grayscale cursor-not-allowed shadow-sm">
                    <div className="w-10 h-10 bg-emerald-100 rounded-xl flex items-center justify-center border border-emerald-200 shadow-inner">
                        <Play size={16} className="text-emerald-700" fill="currentColor" />
                    </div>
                    <div>
                        <p className="text-xs font-black text-emerald-800 uppercase tracking-widest">Start Node</p>
                        <p className="text-[10px] text-emerald-600 font-bold">Already on canvas</p>
                    </div>
                </div>

                <div className="h-px bg-slate-100" />

                {filteredCategories.map(category => (
                    <div key={category.id} className="space-y-2">
                        <button
                            onClick={() => toggleCategory(category.id)}
                            className="w-full flex items-center justify-between text-[10px] font-bold text-slate-400 uppercase tracking-widest hover:text-slate-600 transition-colors group px-1"
                        >
                            <span>{category.label}</span>
                            <motion.div
                                animate={{ rotate: expandedCategories.includes(category.id) ? 0 : -90 }}
                                transition={{ type: "spring", stiffness: 300, damping: 20 }}
                            >
                                <ChevronDown size={12} />
                            </motion.div>
                        </button>

                        <AnimatePresence initial={false}>
                            {expandedCategories.includes(category.id) && (
                                <motion.div
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: "auto", opacity: 1 }}
                                    exit={{ height: 0, opacity: 0 }}
                                    transition={{ duration: 0.2, ease: "easeInOut" }}
                                    className="space-y-2 overflow-hidden"
                                >
                                    {category.elements.map(({ type, label, description, icon: Icon, color }) => {
                                        const colors = colorClasses[color] || colorClasses.white;
                                        return (
                                            <motion.div
                                                key={type}
                                                draggable
                                                onDragStart={(e) => onDragStart(e as any, type)}
                                                whileHover={{ scale: 1.02, y: -2 }}
                                                whileTap={{ scale: 0.98 }}
                                                className={`flex items-center gap-4 p-3.5 rounded-2xl border ${colors.border} bg-white cursor-grab active:cursor-grabbing group transition-all shadow-[0_2px_8px_rgba(0,0,0,0.02)] hover:shadow-[0_8px_24px_rgba(0,0,0,0.06)] hover:border-blue-200`}
                                            >
                                                <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${colors.iconBg} border ${colors.border} group-hover:scale-110 transition-transform`}>
                                                    <Icon size={18} className={colors.text} strokeWidth={2.5} />
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <p className={`text-[12px] font-black uppercase tracking-tight text-slate-800 group-hover:text-blue-600 transition-colors`}>{label}</p>
                                                    <p className="text-[10px] text-slate-400 font-bold truncate mt-0.5">{description}</p>
                                                </div>
                                                <GripVertical size={16} className="text-slate-100 group-hover:text-slate-300 transition-colors" />
                                            </motion.div>
                                        );
                                    })}
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>
                ))}
            </div>

            <div className="h-px bg-slate-100 mt-4" />

            <div className="flex items-center gap-2 p-3 bg-blue-600/5 rounded-xl border border-blue-600/10">
                <MousePointer2 size={12} className="text-blue-400" />
                <p className="text-[10px] text-slate-500 leading-relaxed font-medium">
                    Drag elements onto the canvas to build your flow.
                </p>
            </div>
        </div>
    );
}
