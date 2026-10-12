"use client";

import { useState, useEffect } from "react";
import { Node } from "reactflow";
import { X, Trash2, ChevronDown, Sparkles, Globe, Link2, Slack, Table, Variable, GitBranch } from "lucide-react";
import { BLOCK_NAMES } from "./flowKit";

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
                    <div className="space-y-6">
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Block name</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                                placeholder="Start"
                            />
                        </div>
                    </div>
                );

            case "message":
                return (
                    <div className="space-y-6">
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                            />
                        </div>
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Message</label>
                            <textarea
                                rows={4}
                                value={formData.message || ""}
                                onChange={(e) => handleChange("message", e.target.value)}
                                className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15 resize-none"
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
                const focusColor = "focus:border-plum focus:ring-2 focus:ring-plum/15";
                const toggleBg = "bg-plum";

                return (
                    <div className="space-y-6">
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className={`w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 ${focusColor}`}
                            />
                        </div>
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Question</label>
                            <textarea
                                rows={2}
                                value={formData.message || ""}
                                onChange={(e) => handleChange("message", e.target.value)}
                                className={`w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 resize-none ${focusColor}`}
                                placeholder={node.type === "phoneInput" ? "What's the best number to reach you on?" : "What the assistant asks the visitor"}
                            />
                        </div>
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Placeholder</label>
                            <input
                                type="text"
                                value={formData.placeholder || ""}
                                onChange={(e) => handleChange("placeholder", e.target.value)}
                                className={`w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 ${focusColor}`}
                            />
                        </div>
                        {node.type === "phoneInput" && (
                            <div className="flex items-center justify-between gap-4 p-3 rounded-md border border-line">
                                <div>
                                    <span className="text-[13px] font-medium text-ink">Offer a call back</span>
                                    <p className="text-[12px] text-stone-500 mt-1 leading-relaxed">
                                        Asks &quot;Would you like us to call you now?&quot; and rings them if they say yes. Needs call-backs turned on in Voice.
                                    </p>
                                </div>
                                <button
                                    onClick={() => handleChange("offerCallback", formData.offerCallback === false)}
                                    className={`w-12 h-6 shrink-0 rounded-full transition-all relative ${formData.offerCallback !== false ? toggleBg : "bg-stone-300"}`}
                                >
                                    <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform shadow-sm ${formData.offerCallback !== false ? "left-7" : "left-1"}`} />
                                </button>
                            </div>
                        )}
                        <div className="flex items-center justify-between p-3 rounded-md border border-line">
                            <span className="text-[13px] font-medium text-ink">Required</span>
                            <button
                                onClick={() => handleChange("required", !formData.required)}
                                className={`w-12 h-6 rounded-full transition-all relative ${formData.required ? toggleBg : "bg-stone-300"}`}
                            >
                                <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform shadow-sm ${formData.required ? "left-7" : "left-1"}`} />
                            </button>
                        </div>
                    </div>
                );

            case "image":
            case "video":
                const mediaColor = "focus:border-plum focus:ring-2 focus:ring-plum/15";
                return (
                    <div className="space-y-6">
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className={`w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 ${mediaColor}`}
                            />
                        </div>
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">{node.type === "image" ? "Image URL" : "Video URL"}</label>
                            <input
                                type="text"
                                placeholder="https://..."
                                value={node.type === "image" ? (formData.imageUrl || "") : (formData.videoUrl || "")}
                                onChange={(e) => handleChange(node.type === "image" ? "imageUrl" : "videoUrl", e.target.value)}
                                className={`w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 ${mediaColor}`}
                            />
                        </div>
                    </div>
                );

            case "fileUpload":
                return (
                    <div className="space-y-6">
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                            />
                        </div>
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Instructions</label>
                            <input
                                type="text"
                                value={formData.placeholder || ""}
                                onChange={(e) => handleChange("placeholder", e.target.value)}
                                className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                                placeholder="e.g. Please upload your ID..."
                            />
                        </div>
                    </div>
                );

            case "rating":
                return (
                    <div className="space-y-6">
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                            />
                        </div>
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Max Rating (Scale)</label>
                            <div className="relative">
                                <select
                                    value={formData.scale || 5}
                                    onChange={(e) => handleChange("scale", parseInt(e.target.value))}
                                    className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15 appearance-none cursor-pointer"
                                >
                                    <option value={3}>3 Stars</option>
                                    <option value={5}>5 Stars</option>
                                    <option value={10}>10 Stars</option>
                                </select>
                                <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-stone-400">
                                    <ChevronDown size={16} />
                                </div>
                            </div>
                        </div>
                    </div>
                );

            case "delay":
                return (
                    <div className="space-y-6">
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                            />
                        </div>
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Delay Duration (Seconds)</label>
                            <div className="relative">
                                <input
                                    type="number"
                                    min={0.5}
                                    max={60}
                                    step={0.5}
                                    value={formData.delay || 2}
                                    onChange={(e) => handleChange("delay", parseFloat(e.target.value))}
                                    className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                                />
                                <span className="absolute right-4 top-1/2 -translate-y-1/2 text-[12px] text-stone-400">sec</span>
                            </div>
                        </div>
                    </div>
                );

            case "variable":
                return (
                    <div className="space-y-6">
                        <div className="pt-2">
                             <div className="flex items-center gap-2 mb-4">
                                <Variable size={14} className="text-blue-600" />
                                <p className="text-[12px] font-medium text-stone-500">Set a value</p>
                            </div>
                            <div className="space-y-4">
                                <div>
                                    <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Value name</label>
                                    <input
                                        type="text"
                                        placeholder="e.g. user_tier"
                                        value={formData.variableName || ""}
                                        onChange={(e) => handleChange("variableName", e.target.value)}
                                        className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm font-mono text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                                    />
                                </div>
                                <div>
                                    <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Value to Set</label>
                                    <input
                                        type="text"
                                        placeholder="e.g. platinum"
                                        value={formData.variableValue || ""}
                                        onChange={(e) => handleChange("variableValue", e.target.value)}
                                        className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                                    />
                                </div>
                            </div>
                        </div>
                    </div>
                );

            case "aiPrompt":
                return (
                    <div className="space-y-6">
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Block name</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                            />
                        </div>
                        <div>
                            <div className="flex items-center gap-2 mb-2 px-1">
                                <Sparkles size={14} className="text-cyan-500" />
                                <label className="block text-[12px] font-medium text-stone-500">AI Instructions (System Prompt)</label>
                            </div>
                            <textarea
                                rows={6}
                                placeholder="Explain how the AI should reason or what knowledge it should use for this specific step..."
                                value={formData.prompt || ""}
                                onChange={(e) => handleChange("prompt", e.target.value)}
                                className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15 resize-none leading-relaxed"
                            />
                        </div>
                    </div>
                );

            case "httpRequest":
                return (
                    <div className="space-y-6">
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">API Endpoint (URL)</label>
                            <div className="relative">
                                <Globe size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
                                <input
                                    type="text"
                                    placeholder="https://api.example.com/webhook"
                                    value={formData.url || ""}
                                    onChange={(e) => handleChange("url", e.target.value)}
                                    className="w-full bg-white border border-line-strong rounded-md pl-9 pr-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                                />
                            </div>
                        </div>
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">HTTP Method</label>
                            <div className="relative">
                                <select
                                    value={formData.method || "POST"}
                                    onChange={(e) => handleChange("method", e.target.value)}
                                    className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15 appearance-none cursor-pointer"
                                >
                                    <option value="GET">GET</option>
                                    <option value="POST">POST</option>
                                    <option value="PUT">PUT</option>
                                    <option value="DELETE">DELETE</option>
                                </select>
                                <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-stone-400">
                                    <ChevronDown size={16} />
                                </div>
                            </div>
                        </div>
                    </div>
                );

            case "webhook":
                return (
                    <div className="space-y-6">
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Webhook URL (Zapier/Make)</label>
                            <div className="relative">
                                <Link2 size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
                                <input
                                    type="text"
                                    placeholder="https://hooks.zapier.com/..."
                                    value={formData.url || ""}
                                    onChange={(e) => handleChange("url", e.target.value)}
                                    className="w-full bg-white border border-line-strong rounded-md pl-9 pr-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                                />
                            </div>
                        </div>
                        <div className="p-3 bg-stone-50 border border-line rounded-md">
                            <div className="flex items-center gap-2 mb-1">
                                <Link2 size={12} className="text-orange-600" />
                                <p className="text-[13px] font-medium text-ink">Webhook</p>
                            </div>
                            <p className="text-[12px] text-stone-500 leading-relaxed">
                                This node will send all collected session variables as a JSON payload to the URL above.
                            </p>
                        </div>
                    </div>
                );

            case "slack":
                return (
                    <div className="space-y-6">
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Slack Webhook URL</label>
                            <div className="relative">
                                <Slack size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
                                <input
                                    type="text"
                                    placeholder="https://hooks.slack.com/services/..."
                                    value={formData.url || ""}
                                    onChange={(e) => handleChange("url", e.target.value)}
                                    className="w-full bg-white border border-line-strong rounded-md pl-9 pr-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                                />
                            </div>
                        </div>
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Channel (optional)</label>
                            <input
                                type="text"
                                placeholder="#leads"
                                value={formData.channel || ""}
                                onChange={(e) => handleChange("channel", e.target.value)}
                                className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                            />
                        </div>
                        <div className="p-3 bg-stone-50 border border-line rounded-md">
                            <div className="flex items-center gap-2 mb-1">
                                <Slack size={12} className="text-plum" />
                                <p className="text-[13px] font-medium text-ink">Slack alert</p>
                            </div>
                            <p className="text-[12px] text-stone-500 leading-relaxed">
                                A formatted alert with all captured variables will be sent to this Slack channel.
                            </p>
                        </div>
                    </div>
                );

            case "googleSheets":
                return (
                    <div className="space-y-6">
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Spreadsheet ID</label>
                            <div className="relative">
                                <Table size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
                                <input
                                    type="text"
                                    placeholder="1BxiMVs0..."
                                    value={formData.spreadsheetId || ""}
                                    onChange={(e) => handleChange("spreadsheetId", e.target.value)}
                                    className="w-full bg-white border border-line-strong rounded-md pl-9 pr-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                                />
                            </div>
                        </div>
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Sheet name</label>
                            <input
                                type="text"
                                placeholder="Sheet1"
                                value={formData.sheetName || "Sheet1"}
                                onChange={(e) => handleChange("sheetName", e.target.value)}
                                className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                            />
                        </div>
                        <div className="p-3 bg-stone-50 border border-line rounded-md">
                            <div className="flex items-center gap-2 mb-1">
                                <Table size={12} className="text-emerald-700" />
                                <p className="text-[13px] font-medium text-ink">Google Sheets</p>
                            </div>
                            <p className="text-[12px] text-stone-500 leading-relaxed">
                                Make sure to share your sheet with the service account email provided in settings.
                            </p>
                        </div>
                    </div>
                );

            case "multipleChoice":
                return (
                    <div className="space-y-6">
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Question</label>
                            <input
                                type="text"
                                placeholder="e.g. What are you looking for?"
                                // The widget asks `message`; older flows kept the question in `label`.
                                value={formData.message ?? (["Multiple Choice", "Choices"].includes(formData.label) ? "" : formData.label || "")}
                                onChange={(e) => handleChange("message", e.target.value)}
                                className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                            />
                        </div>
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Options</label>
                            <div className="space-y-3">
                                {(formData.options || []).map((option: string, index: number) => (
                                    <div key={index} className="flex gap-2 group/opt">
                                        <input
                                            type="text"
                                            value={option}
                                            onChange={(e) => handleOptionsChange(index, e.target.value)}
                                            className="flex-1 bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                                        />
                                        <button
                                            onClick={() => removeOption(index)}
                                            className="p-2 text-stone-400 hover:text-signal hover:bg-red-50 rounded-md"
                                        >
                                            <X size={16} strokeWidth={2.5} />
                                        </button>
                                    </div>
                                ))}
                                <button
                                    onClick={addOption}
                                    className="w-full h-9 border border-dashed border-line-strong rounded-md text-[13px] text-stone-600 hover:text-ink hover:border-stone-400"
                                >
                                    + Add option
                                </button>
                            </div>
                        </div>
                        <div className="flex items-center justify-between p-3 rounded-md border border-line">
                            <span className="text-[13px] font-medium text-ink">Required</span>
                            <button
                                onClick={() => handleChange("required", !formData.required)}
                                className={`w-12 h-6 rounded-full transition-all relative ${formData.required ? "bg-plum" : "bg-stone-300"}`}
                            >
                                <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform shadow-sm ${formData.required ? "left-7" : "left-1"}`} />
                            </button>
                        </div>
                    </div>
                );

            case "condition":
                return (
                    <div className="space-y-6">
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Block name</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                            />
                        </div>
                        <div className="pt-4 border-t border-line">
                            <div className="flex items-center gap-2 mb-4 px-1">
                                <GitBranch size={14} className="text-plum" />
                                <p className="text-[12px] font-medium text-stone-500">Rule</p>
                            </div>
                            <div className="space-y-4">
                                <div>
                                    <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Check this answer</label>
                                    <input
                                        type="text"
                                        placeholder="e.g. user_choice"
                                        value={formData.variable || ""}
                                        onChange={(e) => handleChange("variable", e.target.value)}
                                        className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm font-mono text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                                    />
                                </div>
                                <div>
                                    <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Operator</label>
                                    <div className="relative">
                                        <select
                                            value={formData.operator || "equals"}
                                            onChange={(e) => handleChange("operator", e.target.value)}
                                            className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15 appearance-none cursor-pointer"
                                        >
                                            <option value="equals">Equals</option>
                                            <option value="contains">Contains</option>
                                            <option value="greater_than">Greater than</option>
                                            <option value="less_than">Less than</option>
                                        </select>
                                        <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-stone-400">
                                            <ChevronDown size={16} />
                                        </div>
                                    </div>
                                </div>
                                <div>
                                    <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Value</label>
                                    <input
                                        type="text"
                                        placeholder="Value to compare..."
                                        value={formData.value || ""}
                                        onChange={(e) => handleChange("value", e.target.value)}
                                        className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                                    />
                                </div>
                            </div>
                        </div>
                    </div>
                );

            case "end":
                return (
                    <div className="space-y-6">
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Block name</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                            />
                        </div>
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Closing message</label>
                            <textarea
                                rows={4}
                                value={formData.message || ""}
                                onChange={(e) => handleChange("message", e.target.value)}
                                className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15 resize-none"
                                placeholder="Final message to the user..."
                            />
                        </div>
                    </div>
                );

            case "handover":
                return (
                    <div className="space-y-6">
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Label</label>
                            <input
                                type="text"
                                value={formData.label || ""}
                                onChange={(e) => handleChange("label", e.target.value)}
                                className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15"
                            />
                        </div>
                        <div>
                            <label className="block text-[13px] font-medium text-stone-700 mb-1.5">Message before handing over</label>
                            <textarea
                                rows={4}
                                value={formData.message || ""}
                                onChange={(e) => handleChange("message", e.target.value)}
                                className="w-full bg-white border border-line-strong rounded-md px-3 py-2 text-sm text-ink placeholder:text-stone-400 outline-none hover:border-stone-400 focus:border-plum focus:ring-2 focus:ring-plum/15 resize-none"
                                placeholder="e.g. Please wait while I connect you to a human agent..."
                            />
                        </div>
                        <div className="p-3 bg-stone-50 border border-line rounded-md">
                            <p className="text-[12px] text-stone-500 leading-relaxed">
                                This node will flag the conversation for human intervention and notify the bot owner.
                            </p>
                        </div>
                    </div>
                );

            default:
                return null;
        }
    };

    return (
        <div className="space-y-5">
            <div className="flex items-center justify-between">
                <div>
                     <h3 className="text-sm font-semibold text-ink">Block settings</h3>
                     <p className="text-[12px] text-stone-500">{BLOCK_NAMES[node.type as string] ?? node.type}</p>
                </div>
                <button 
                    onClick={onClose} 
                    aria-label="Close block settings" className="p-1.5 -m-1.5 rounded text-stone-400 hover:text-ink group"
                >
                    <X size={16} />
                </button>
            </div>

            <div className="h-px bg-line" />

            {renderFields()}

            {node.type !== "start" && (
                <div className="pt-5 border-t border-line space-y-3">
                    <button
                        onClick={() => onDelete(node.id)}
                        className="w-full inline-flex items-center justify-center gap-1.5 h-9 bg-white text-signal border border-line-strong rounded-md text-[13px] hover:bg-red-50 hover:border-red-200 group"
                    >
                        <Trash2 size={14} className="group-hover:scale-110 transition-transform" strokeWidth={2.5} />
                        Delete block
                    </button>
                    <p className="text-[11px] text-stone-400 text-center">
                        Block ID: {node.id.slice(0, 8)}
                    </p>
                </div>
            )}
        </div>
    );
}
