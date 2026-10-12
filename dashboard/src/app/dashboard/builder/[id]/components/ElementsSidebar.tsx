"use client";

import { useState, DragEvent } from "react";
import {
    MessageSquare, Type, Mail, List, Square, GripVertical, GitBranch, Hash, Image as ImageIcon, Video,
    Upload, Star, Clock, Variable, Globe, Sparkles, Phone, Link2, Slack, Table, ChevronDown, Search, UserPlus,
} from "lucide-react";
import { cn } from "@/components/ui";

const categories = [
    {
        id: "basic",
        label: "Ask and tell",
        elements: [
            { type: "message", label: "Message", description: "Send a message", icon: MessageSquare },
            { type: "textInput", label: "Text", description: "Ask for a written answer", icon: Type },
            { type: "emailInput", label: "Email", description: "Ask for an email address", icon: Mail },
            { type: "numberInput", label: "Number", description: "Ask for a number", icon: Hash },
            { type: "phoneInput", label: "Phone", description: "Ask for a phone number", icon: Phone },
            { type: "multipleChoice", label: "Choices", description: "Offer buttons to pick from", icon: List },
        ],
    },
    {
        id: "media",
        label: "Media",
        elements: [
            { type: "image", label: "Image", description: "Show an image", icon: ImageIcon },
            { type: "video", label: "Video", description: "Show a video", icon: Video },
            { type: "fileUpload", label: "File upload", description: "Ask for a file", icon: Upload },
            { type: "rating", label: "Rating", description: "Ask for a score", icon: Star },
        ],
    },
    {
        id: "logic",
        label: "Logic",
        elements: [
            { type: "condition", label: "Condition", description: "Branch on an answer", icon: GitBranch },
            { type: "handover", label: "Hand to a person", description: "Bring in your team", icon: UserPlus },
            { type: "delay", label: "Wait", description: "Pause for a few seconds", icon: Clock },
            { type: "variable", label: "Set value", description: "Remember something", icon: Variable },
            { type: "end", label: "End", description: "Finish the flow", icon: Square },
        ],
    },
    {
        id: "advanced",
        label: "AI and integrations",
        elements: [
            { type: "aiPrompt", label: "AI step", description: "Let the AI write a reply", icon: Sparkles },
            { type: "httpRequest", label: "HTTP request", description: "Fetch data from a link", icon: Globe },
            { type: "webhook", label: "Webhook", description: "Send answers to Zapier or Make", icon: Link2 },
            { type: "slack", label: "Slack", description: "Post a lead to Slack", icon: Slack },
            { type: "googleSheets", label: "Google Sheets", description: "Add a row to a sheet", icon: Table },
        ],
    },
];

export default function ElementsSidebar() {
    const [query, setQuery] = useState("");
    const [collapsed, setCollapsed] = useState<string[]>([]);

    const onDragStart = (event: DragEvent, nodeType: string) => {
        event.dataTransfer.setData("application/reactflow", nodeType);
        event.dataTransfer.effectAllowed = "move";
    };

    const q = query.trim().toLowerCase();
    const shown = categories
        .map((c) => ({ ...c, elements: c.elements.filter((el) => !q || el.label.toLowerCase().includes(q) || el.description.toLowerCase().includes(q)) }))
        .filter((c) => c.elements.length > 0);

    return (
        <div>
            <p className="text-[12px] text-stone-500 mb-3">Drag a block onto the canvas, then connect it.</p>
            <div className="relative mb-4">
                <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-stone-400" aria-hidden />
                <input
                    type="search"
                    placeholder="Search blocks"
                    aria-label="Search blocks"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    className="w-full h-9 pl-8 pr-3 rounded-md border border-line-strong bg-white text-sm text-ink placeholder:text-stone-400 hover:border-stone-400 focus:outline-none focus:border-plum focus:ring-2 focus:ring-plum/15"
                />
            </div>

            <div className="space-y-4">
                {shown.map((category) => {
                    const open = q !== "" || !collapsed.includes(category.id);
                    return (
                        <div key={category.id}>
                            <button
                                type="button"
                                aria-expanded={open}
                                onClick={() => setCollapsed((c) => (c.includes(category.id) ? c.filter((x) => x !== category.id) : [...c, category.id]))}
                                className="w-full flex items-center justify-between py-1 text-[12px] font-medium text-stone-500 hover:text-ink"
                            >
                                {category.label}
                                <ChevronDown size={14} className={cn("transition-transform", !open && "-rotate-90")} />
                            </button>
                            {open && (
                                <div className="mt-1 space-y-1">
                                    {category.elements.map(({ type, label, description, icon: Icon }) => (
                                        <div
                                            key={type}
                                            draggable
                                            onDragStart={(e) => onDragStart(e, type)}
                                            className="group flex items-center gap-3 px-2 py-2 rounded-md border border-transparent hover:border-line hover:bg-stone-50 cursor-grab active:cursor-grabbing"
                                        >
                                            <span className="h-8 w-8 shrink-0 rounded-md bg-stone-100 flex items-center justify-center text-stone-600">
                                                <Icon size={15} />
                                            </span>
                                            <span className="min-w-0 flex-1">
                                                <span className="block text-[13px] font-medium text-ink">{label}</span>
                                                <span className="block text-[12px] text-stone-500 truncate">{description}</span>
                                            </span>
                                            <GripVertical size={14} className="text-stone-300 opacity-0 group-hover:opacity-100" aria-hidden />
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    );
                })}
                {!shown.length && <p className="text-[13px] text-stone-500 py-4 text-center">No blocks match “{query}”.</p>}
            </div>
        </div>
    );
}
