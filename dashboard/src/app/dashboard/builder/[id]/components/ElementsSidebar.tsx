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

const colorClasses: Record<string, { bg: string; text: string; border: string }> = {
    green: { bg: "bg-green-500/10", text: "text-green-400", border: "border-green-500/20" },
    blue: { bg: "bg-blue-500/10", text: "text-blue-400", border: "border-blue-500/20" },
    purple: { bg: "bg-purple-500/10", text: "text-purple-400", border: "border-purple-500/20" },
    cyan: { bg: "bg-cyan-500/10", text: "text-cyan-400", border: "border-cyan-500/20" },
    amber: { bg: "bg-amber-500/10", text: "text-amber-400", border: "border-amber-500/20" },
    pink: { bg: "bg-pink-500/10", text: "text-pink-400", border: "border-pink-500/20" },
    red: { bg: "bg-red-500/10", text: "text-red-400", border: "border-red-500/20" },
    orange: { bg: "bg-orange-500/10", text: "text-orange-400", border: "border-orange-500/20" },
    white: { bg: "bg-white/10", text: "text-white", border: "border-white/20" },
    indigo: { bg: "bg-indigo-500/10", text: "text-indigo-400", border: "border-indigo-500/20" },
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
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
                <input
                    type="text"
                    placeholder="Search elements..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full bg-white/5 border border-white/10 rounded-xl pl-9 pr-4 py-2 text-xs outline-none focus:border-blue-500 transition-colors"
                />
            </div>

            <div className="space-y-4">
                {/* Start Node Indicator */}
                <div className="flex items-center gap-3 p-3 rounded-xl bg-green-500/10 border border-green-500/20 opacity-60 grayscale cursor-not-allowed">
                    <div className="w-8 h-8 bg-green-500/20 rounded-lg flex items-center justify-center">
                        <Play size={14} className="text-green-400" fill="currentColor" />
                    </div>
                    <div>
                        <p className="text-xs font-bold text-green-400">Start Node</p>
                        <p className="text-[10px] text-green-400/50">Already on canvas</p>
                    </div>
                </div>

                <div className="h-px bg-white/5" />

                {filteredCategories.map(category => (
                    <div key={category.id} className="space-y-2">
                        <button
                            onClick={() => toggleCategory(category.id)}
                            className="w-full flex items-center justify-between text-[10px] font-bold text-white/30 uppercase tracking-widest hover:text-white/50 transition-colors group px-1"
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
                                                whileHover={{ scale: 1.02 }}
                                                whileTap={{ scale: 0.98 }}
                                                className={`flex items-center gap-3 p-3 rounded-xl border ${colors.border} ${colors.bg} cursor-grab active:cursor-grabbing group transition-all`}
                                            >
                                                <GripVertical size={14} className="text-white/10 group-hover:text-white/30 transition-colors" />
                                                <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${colors.bg} border ${colors.border}`}>
                                                    <Icon size={14} className={colors.text} />
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <p className={`text-xs font-bold ${colors.text}`}>{label}</p>
                                                    <p className="text-[10px] text-white/30 truncate">{description}</p>
                                                </div>
                                            </motion.div>
                                        );
                                    })}
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>
                ))}
            </div>

            <div className="h-px bg-white/5 mt-4" />

            <div className="flex items-center gap-2 p-3 bg-blue-600/5 rounded-xl border border-blue-600/10">
                <MousePointer2 size={12} className="text-blue-400" />
                <p className="text-[10px] text-white/40 leading-relaxed">
                    Drag elements onto the canvas to build your flow.
                </p>
            </div>
        </div>
    );
}
