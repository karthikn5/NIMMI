"use client";

import { useState, useEffect } from "react";
import { Node } from "reactflow";
import { X, Trash2, ChevronDown, Sparkles, Globe, Link2, Slack, Table, Variable, GitBranch } from "lucide-react";

interface PropertiesPanelProps {
    node: Node | null;
    onUpdate: (nodeId: string, data: any) => void;
    onDelete: (nodeId: string) => void;
    onClose: () => void;
}

export default function PropertiesPanel({ node, onUpdate, onDelete, onClose }: PropertiesPanelProps) {
    const [formData, setFormData] = useState<any>({});

    useEffect(() => {
        if (node) {
            setFormData(node.data);
        }
    }, [node]);

    if (!node) return null;

    const handleChange = (key: string, value: any) => {
        const newData = { ...formData, [key]: value };
        setFormData(newData);
        onUpdate(node.id, newData);
    };

    const handleOptionsChange = (index: number, value: string) => {
        const newOptions = [...(formData.options || [])];
        newOptions[index] = value;
        handleChange("options", newOptions);
    };

    const addOption = () => {
        const newOptions = [...(formData.options || []), `Option ${(formData.options?.length || 0) + 1}`];
        handleChange("options", newOptions);
    };

    const removeOption = (index: number) => {
        const newOptions = (formData.options || []).filter((_: string, i: number) => i !== index);
        handleChange("options", newOptions);
    };

    const renderFields = () => {
        switch (node.type) {
            case "start":
                return (
                    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Node Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/5 transition-all shadow-sm"
                                placeholder="Start"
                            />
                        </div>
                    </div>
                );

            case "message":
                return (
                    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/5 transition-all shadow-sm"
                            />
                        </div>
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Message Content</label>
                            <textarea
                                rows={4}
                                value={formData.message || ""}
                                onChange={(e) => handleChange("message", e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/5 transition-all shadow-sm resize-none"
                                placeholder="Type the bot message here..."
                            />
                        </div>
                    </div>
                );

            case "textInput":
            case "emailInput":
            case "datePicker":
            case "numberInput":
            case "phoneInput":
                const focusColor = node.type === "numberInput" ? "focus:border-orange-500 focus:ring-orange-500/5" : (node.type === "phoneInput" ? "focus:border-green-500 focus:ring-green-500/5" : "focus:border-purple-500 focus:ring-purple-500/5");
                const toggleBg = node.type === "numberInput" ? "bg-orange-500" : (node.type === "phoneInput" ? "bg-emerald-500" : "bg-purple-500");

                return (
                    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className={`w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none transition-all shadow-sm ${focusColor}`}
                            />
                        </div>
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Placeholder</label>
                            <input
                                type="text"
                                value={formData.placeholder || ""}
                                onChange={(e) => handleChange("placeholder", e.target.value)}
                                className={`w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none transition-all shadow-sm ${focusColor}`}
                            />
                        </div>
                        <div className="flex items-center justify-between p-4 bg-slate-50 rounded-2xl border border-slate-100 shadow-sm">
                            <span className="text-[11px] font-black text-slate-900 uppercase tracking-wider">Required Field</span>
                            <button
                                onClick={() => handleChange("required", !formData.required)}
                                className={`w-12 h-6 rounded-full transition-all relative ${formData.required ? toggleBg : "bg-slate-200"}`}
                            >
                                <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform shadow-sm ${formData.required ? "left-7" : "left-1"}`} />
                            </button>
                        </div>
                    </div>
                );

            case "image":
            case "video":
                const mediaColor = node.type === "image" ? "focus:border-pink-500 focus:ring-pink-500/5" : "focus:border-red-500 focus:ring-red-500/5";
                return (
                    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className={`w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none transition-all shadow-sm ${mediaColor}`}
                            />
                        </div>
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">{node.type === "image" ? "Image URL" : "Video URL"}</label>
                            <input
                                type="text"
                                placeholder="https://..."
                                value={node.type === "image" ? (formData.imageUrl || "") : (formData.videoUrl || "")}
                                onChange={(e) => handleChange(node.type === "image" ? "imageUrl" : "videoUrl", e.target.value)}
                                className={`w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none transition-all shadow-sm ${mediaColor}`}
                            />
                        </div>
                    </div>
                );

            case "fileUpload":
                return (
                    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-500/5 transition-all shadow-sm"
                            />
                        </div>
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Instructions</label>
                            <input
                                type="text"
                                value={formData.placeholder || ""}
                                onChange={(e) => handleChange("placeholder", e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-500/5 transition-all shadow-sm"
                                placeholder="e.g. Please upload your ID..."
                            />
                        </div>
                    </div>
                );

            case "rating":
                return (
                    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-amber-500 focus:ring-4 focus:ring-amber-500/5 transition-all shadow-sm"
                            />
                        </div>
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Max Rating (Scale)</label>
                            <div className="relative">
                                <select
                                    value={formData.scale || 5}
                                    onChange={(e) => handleChange("scale", parseInt(e.target.value))}
                                    className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-amber-500 focus:ring-4 focus:ring-amber-500/5 transition-all shadow-sm appearance-none cursor-pointer"
                                >
                                    <option value={3}>3 Stars</option>
                                    <option value={5}>5 Stars</option>
                                    <option value={10}>10 Stars</option>
                                </select>
                                <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400">
                                    <ChevronDown size={16} />
                                </div>
                            </div>
                        </div>
                    </div>
                );

            case "delay":
                return (
                    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-slate-500 focus:ring-4 focus:ring-slate-500/5 transition-all shadow-sm"
                            />
                        </div>
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Delay Duration (Seconds)</label>
                            <div className="relative">
                                <input
                                    type="number"
                                    min={0.5}
                                    max={60}
                                    step={0.5}
                                    value={formData.delay || 2}
                                    onChange={(e) => handleChange("delay", parseFloat(e.target.value))}
                                    className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/5 transition-all shadow-sm"
                                />
                                <span className="absolute right-4 top-1/2 -translate-y-1/2 text-[10px] font-black text-slate-300 uppercase tracking-widest">Sec</span>
                            </div>
                        </div>
                    </div>
                );

            case "variable":
                return (
                    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                        <div className="pt-2">
                             <div className="flex items-center gap-2 mb-4">
                                <Variable size={14} className="text-blue-600" />
                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Set Local Variable</p>
                            </div>
                            <div className="space-y-4">
                                <div>
                                    <label className="block text-[10px] font-black text-slate-400 mb-2 tracking-widest uppercase px-1">Variable Name</label>
                                    <input
                                        type="text"
                                        placeholder="e.g. user_tier"
                                        value={formData.variableName || ""}
                                        onChange={(e) => handleChange("variableName", e.target.value)}
                                        className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-mono font-bold text-slate-900 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/5 transition-all shadow-sm"
                                    />
                                </div>
                                <div>
                                    <label className="block text-[10px] font-black text-slate-400 mb-2 tracking-widest uppercase px-1">Value to Set</label>
                                    <input
                                        type="text"
                                        placeholder="e.g. platinum"
                                        value={formData.variableValue || ""}
                                        onChange={(e) => handleChange("variableValue", e.target.value)}
                                        className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/5 transition-all shadow-sm"
                                    />
                                </div>
                            </div>
                        </div>
                    </div>
                );

            case "aiPrompt":
                return (
                    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Step Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-cyan-500 focus:ring-4 focus:ring-cyan-500/5 transition-all shadow-sm"
                            />
                        </div>
                        <div>
                            <div className="flex items-center gap-2 mb-2 px-1">
                                <Sparkles size={14} className="text-cyan-500" />
                                <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest">AI Instructions (System Prompt)</label>
                            </div>
                            <textarea
                                rows={6}
                                placeholder="Explain how the AI should reason or what knowledge it should use for this specific step..."
                                value={formData.prompt || ""}
                                onChange={(e) => handleChange("prompt", e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-cyan-500 focus:ring-4 focus:ring-cyan-500/5 transition-all shadow-sm resize-none leading-relaxed"
                            />
                        </div>
                    </div>
                );

            case "httpRequest":
                return (
                    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">API Endpoint (URL)</label>
                            <div className="relative">
                                <Globe size={14} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                <input
                                    type="text"
                                    placeholder="https://api.example.com/webhook"
                                    value={formData.url || ""}
                                    onChange={(e) => handleChange("url", e.target.value)}
                                    className="w-full bg-slate-50 border border-slate-200 rounded-2xl pl-11 pr-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-emerald-500 focus:ring-4 focus:ring-emerald-500/5 transition-all shadow-sm"
                                />
                            </div>
                        </div>
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">HTTP Method</label>
                            <div className="relative">
                                <select
                                    value={formData.method || "POST"}
                                    onChange={(e) => handleChange("method", e.target.value)}
                                    className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-emerald-500 focus:ring-4 focus:ring-emerald-500/5 transition-all shadow-sm appearance-none cursor-pointer"
                                >
                                    <option value="GET">GET</option>
                                    <option value="POST">POST</option>
                                    <option value="PUT">PUT</option>
                                    <option value="DELETE">DELETE</option>
                                </select>
                                <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400">
                                    <ChevronDown size={16} />
                                </div>
                            </div>
                        </div>
                    </div>
                );

            case "webhook":
                return (
                    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Webhook URL (Zapier/Make)</label>
                            <div className="relative">
                                <Link2 size={14} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                <input
                                    type="text"
                                    placeholder="https://hooks.zapier.com/..."
                                    value={formData.url || ""}
                                    onChange={(e) => handleChange("url", e.target.value)}
                                    className="w-full bg-slate-50 border border-slate-200 rounded-2xl pl-11 pr-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-orange-500 focus:ring-4 focus:ring-orange-500/5 transition-all shadow-sm"
                                />
                            </div>
                        </div>
                        <div className="p-4 bg-orange-50/50 border border-orange-100 rounded-2xl shadow-sm">
                            <div className="flex items-center gap-2 mb-1">
                                <Link2 size={12} className="text-orange-600" />
                                <p className="text-[10px] text-orange-700 font-black uppercase tracking-widest">Webhook Integration</p>
                            </div>
                            <p className="text-[10px] text-slate-500 font-bold leading-relaxed">
                                This node will send all collected session variables as a JSON payload to the URL above.
                            </p>
                        </div>
                    </div>
                );

            case "slack":
                return (
                    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Slack Webhook URL</label>
                            <div className="relative">
                                <Slack size={14} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                <input
                                    type="text"
                                    placeholder="https://hooks.slack.com/services/..."
                                    value={formData.url || ""}
                                    onChange={(e) => handleChange("url", e.target.value)}
                                    className="w-full bg-slate-50 border border-slate-200 rounded-2xl pl-11 pr-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-purple-500 focus:ring-4 focus:ring-purple-500/5 transition-all shadow-sm"
                                />
                            </div>
                        </div>
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Channel (optional)</label>
                            <input
                                type="text"
                                placeholder="#leads"
                                value={formData.channel || ""}
                                onChange={(e) => handleChange("channel", e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-purple-500 focus:ring-4 focus:ring-purple-500/5 transition-all shadow-sm"
                            />
                        </div>
                        <div className="p-4 bg-purple-50/50 border border-purple-100 rounded-2xl shadow-sm">
                            <div className="flex items-center gap-2 mb-1">
                                <Slack size={12} className="text-purple-600" />
                                <p className="text-[10px] text-purple-700 font-black uppercase tracking-widest">Slack Alert</p>
                            </div>
                            <p className="text-[10px] text-slate-500 font-bold leading-relaxed">
                                A formatted alert with all captured variables will be sent to this Slack channel.
                            </p>
                        </div>
                    </div>
                );

            case "googleSheets":
                return (
                    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Spreadsheet ID</label>
                            <div className="relative">
                                <Table size={14} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                <input
                                    type="text"
                                    placeholder="1BxiMVs0..."
                                    value={formData.spreadsheetId || ""}
                                    onChange={(e) => handleChange("spreadsheetId", e.target.value)}
                                    className="w-full bg-slate-50 border border-slate-200 rounded-2xl pl-11 pr-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-emerald-500 focus:ring-4 focus:ring-emerald-500/5 transition-all shadow-sm"
                                />
                            </div>
                        </div>
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Sheet Name</label>
                            <input
                                type="text"
                                placeholder="Sheet1"
                                value={formData.sheetName || "Sheet1"}
                                onChange={(e) => handleChange("sheetName", e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-emerald-500 focus:ring-4 focus:ring-emerald-500/5 transition-all shadow-sm"
                            />
                        </div>
                        <div className="p-4 bg-emerald-50/50 border border-emerald-100 rounded-2xl shadow-sm">
                            <div className="flex items-center gap-2 mb-1">
                                <Table size={12} className="text-emerald-700" />
                                <p className="text-[10px] text-emerald-800 font-black uppercase tracking-widest">Google Sheets Sync</p>
                            </div>
                            <p className="text-[10px] text-slate-500 font-bold leading-relaxed">
                                Make sure to share your sheet with the service account email provided in settings.
                            </p>
                        </div>
                    </div>
                );

            case "multipleChoice":
                return (
                    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Question/Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-amber-500 focus:ring-4 focus:ring-amber-500/5 transition-all shadow-sm"
                            />
                        </div>
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Options</label>
                            <div className="space-y-3">
                                {(formData.options || []).map((option: string, index: number) => (
                                    <div key={index} className="flex gap-2 group/opt">
                                        <input
                                            type="text"
                                            value={option}
                                            onChange={(e) => handleOptionsChange(index, e.target.value)}
                                            className="flex-1 bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 text-sm font-bold text-slate-900 outline-none focus:border-amber-500 transition-all shadow-sm"
                                        />
                                        <button
                                            onClick={() => removeOption(index)}
                                            className="p-2 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-xl transition-all"
                                        >
                                            <X size={16} strokeWidth={2.5} />
                                        </button>
                                    </div>
                                ))}
                                <button
                                    onClick={addOption}
                                    className="w-full py-3 bg-amber-50 text-amber-700 border border-amber-100 border-dashed rounded-2xl text-[10px] font-black uppercase tracking-widest hover:bg-amber-100 hover:border-amber-200 transition-all active:scale-95"
                                >
                                    + Add Option
                                </button>
                            </div>
                        </div>
                        <div className="flex items-center justify-between p-4 bg-slate-50 rounded-2xl border border-slate-100 shadow-sm">
                            <span className="text-[11px] font-black text-slate-900 uppercase tracking-wider">Required Field</span>
                            <button
                                onClick={() => handleChange("required", !formData.required)}
                                className={`w-12 h-6 rounded-full transition-all relative ${formData.required ? "bg-amber-500" : "bg-slate-200"}`}
                            >
                                <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform shadow-sm ${formData.required ? "left-7" : "left-1"}`} />
                            </button>
                        </div>
                    </div>
                );

            case "condition":
                return (
                    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Logic Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-purple-500 focus:ring-4 focus:ring-purple-500/5 transition-all shadow-sm"
                            />
                        </div>
                        <div className="pt-4 border-t border-slate-100">
                            <div className="flex items-center gap-2 mb-4 px-1">
                                <GitBranch size={14} className="text-purple-600" />
                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Rules Definition</p>
                            </div>
                            <div className="space-y-4">
                                <div>
                                    <label className="block text-[10px] font-black text-slate-400 mb-2 tracking-widest uppercase px-1">Check Variable</label>
                                    <input
                                        type="text"
                                        placeholder="e.g. user_choice"
                                        value={formData.variable || ""}
                                        onChange={(e) => handleChange("variable", e.target.value)}
                                        className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-mono font-bold text-slate-900 outline-none focus:border-purple-500 focus:ring-4 focus:ring-purple-500/5 transition-all shadow-sm"
                                    />
                                </div>
                                <div>
                                    <label className="block text-[10px] font-black text-slate-400 mb-2 tracking-widest uppercase px-1">Operator</label>
                                    <div className="relative">
                                        <select
                                            value={formData.operator || "equals"}
                                            onChange={(e) => handleChange("operator", e.target.value)}
                                            className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-purple-500 focus:ring-4 focus:ring-purple-500/5 transition-all shadow-sm appearance-none cursor-pointer"
                                        >
                                            <option value="equals">Equals</option>
                                            <option value="contains">Contains</option>
                                            <option value="greater_than">Greater Than</option>
                                            <option value="less_than">Less Than</option>
                                        </select>
                                        <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400">
                                            <ChevronDown size={16} />
                                        </div>
                                    </div>
                                </div>
                                <div>
                                    <label className="block text-[10px] font-black text-slate-400 mb-2 tracking-widest uppercase px-1">Target Value</label>
                                    <input
                                        type="text"
                                        placeholder="Value to compare..."
                                        value={formData.value || ""}
                                        onChange={(e) => handleChange("value", e.target.value)}
                                        className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-purple-500 focus:ring-4 focus:ring-purple-500/5 transition-all shadow-sm"
                                    />
                                </div>
                            </div>
                        </div>
                    </div>
                );

            case "end":
                return (
                    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Flow Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-rose-500 focus:ring-4 focus:ring-rose-500/5 transition-all shadow-sm"
                            />
                        </div>
                        <div>
                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Thank You Message</label>
                            <textarea
                                rows={4}
                                value={formData.message || ""}
                                onChange={(e) => handleChange("message", e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:border-rose-500 focus:ring-4 focus:ring-rose-500/5 transition-all shadow-sm resize-none"
                                placeholder="Final message to the user..."
                            />
                        </div>
                    </div>
                );

            default:
                return null;
        }
    };

    return (
        <div className="bg-white border border-slate-200 rounded-[32px] p-6 space-y-6 h-full overflow-y-auto custom-scrollbar shadow-xl border-l-4 border-l-blue-600/10">
            <div className="flex items-center justify-between">
                <div>
                     <h3 className="text-base font-black text-slate-900 uppercase tracking-widest">Properties</h3>
                     <p className="text-[10px] text-slate-400 font-bold uppercase tracking-tighter">Configure {node.type} step</p>
                </div>
                <button 
                    onClick={onClose} 
                    className="p-2 hover:bg-slate-50 rounded-xl transition-colors border border-transparent hover:border-slate-100 group"
                >
                    <X size={18} className="text-slate-300 group-hover:text-slate-900 transition-colors" strokeWidth={2.5} />
                </button>
            </div>

            <div className="h-px bg-slate-100" />

            {renderFields()}

            {node.type !== "start" && (
                <div className="pt-6 border-t border-slate-100 space-y-4">
                    <button
                        onClick={() => onDelete(node.id)}
                        className="w-full flex items-center justify-center gap-2 py-4 bg-rose-50 text-rose-600 border border-rose-100 rounded-2xl text-[10px] font-black uppercase tracking-widest hover:bg-rose-600 hover:text-white transition-all shadow-sm active:scale-95 group"
                    >
                        <Trash2 size={14} className="group-hover:scale-110 transition-transform" strokeWidth={2.5} />
                        Delete Element
                    </button>
                    <p className="text-[9px] text-slate-300 text-center font-bold uppercase tracking-tighter">
                        Node ID: {node.id.slice(0, 8)}
                    </p>
                </div>
            )}
        </div>
    );
}
