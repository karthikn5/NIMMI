"use client";

import { useState, useEffect } from "react";
import { X, Copy, Check, Code, Terminal, Layers, Lock, ShieldCheck, Zap } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface ExportModalProps {
    botId: string;
    onClose: () => void;
}

export default function ExportModal({ botId, onClose }: ExportModalProps) {
    const [copied, setCopied] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<"html" | "react" | "nextjs">("html");
    const [exporting, setExporting] = useState(false);
    const [isUnlocked, setIsUnlocked] = useState(false);
    const [checkingStatus, setCheckingStatus] = useState(true);
    const [subscription, setSubscription] = useState<any>(null);

    const apiBase = typeof window !== "undefined" && window.location.hostname.includes("nimmiai.in")
        ? "https://api.nimmiai.in"
        : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");
    const scriptUrl = `${apiBase}/static/nimmi-widget.js?v=2.0`;

    useEffect(() => {
        const userId = localStorage.getItem("nimmi_user_id");
        if (!userId) return;

        const checkStatus = async () => {
            try {
                const cleanUserId = userId.trim();
                const configRes = await fetch(`${apiBase}/api/bots/${botId}/config?user_id=${cleanUserId}`);
                
                if (configRes.ok) {
                    const configData = await configRes.json();
                    setIsUnlocked(configData.is_exported);
                    setSubscription(configData.subscription);
                }
            } catch (err) {
                console.error("Failed to check status:", err);
            } finally {
                setCheckingStatus(false);
            }
        };
        checkStatus();
    }, [botId, apiBase]);

    const handleExport = async () => {
        const userId = localStorage.getItem("nimmi_user_id");
        if (!userId) return;

        setExporting(true);
        try {
            const res = await fetch(`${apiBase}/api/bots/export?bot_id=${botId}&user_id=${userId}`, {
                method: 'POST'
            });
            const data = await res.json();

            if (res.ok) {
                setIsUnlocked(true);
                alert("Bot plan verified! Export unlocked.");
            } else {
                alert("Verification failed: " + (data.detail || "Unknown error"));
                if (res.status === 402) {
                    window.location.href = "/dashboard/billing";
                }
            }
        } catch (err) {
            console.error("Verification error:", err);
            alert("Verification failed. Please try again.");
        } finally {
            setExporting(false);
        }
    };

    const snippets = {
        html: `<!-- Nimmi AI Chatbot -->
<script 
  src="${scriptUrl}" 
  data-bot-id="${botId}" 
  data-api-url="${apiBase}"
  defer
></script>`,
        react: `import { useEffect } from 'react';

export default function NimmiChat() {
  useEffect(() => {
    const script = document.createElement('script');
    script.src = "${scriptUrl}";
    script.setAttribute('data-bot-id', '${botId}');
    script.setAttribute('data-api-url', '${apiBase}');
    script.defer = true;
    document.body.appendChild(script);
    
    return () => {
      if (document.body.contains(script)) {
        document.body.removeChild(script);
      }
    };
  }, []);

  return null;
}

// Usage: <NimmiChat />`,
        nextjs: `"use client";

import Script from 'next/script';

export default function NimmiChatbot() {
  return (
    <Script
      src="${scriptUrl}"
      data-bot-id="${botId}"
      data-api-url="${apiBase}"
      strategy="afterInteractive"
    />
  );
}`
    };

    const handleCopy = (type: string, text: string) => {
        navigator.clipboard.writeText(text);
        setCopied(type);
        setTimeout(() => setCopied(null), 2000);
    };

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
            <div className="bg-white/90 backdrop-blur-2xl border border-white/40 rounded-[32px] w-full max-w-2xl overflow-hidden shadow-[0_20px_50px_rgba(0,0,0,0.1)] flex flex-col max-h-[90vh] ring-1 ring-black/5">
                <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-white/50 backdrop-blur-md sticky top-0 z-10">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-blue-50 rounded-xl flex items-center justify-center border border-blue-100 shadow-inner">
                            <Code size={20} className="text-blue-600" />
                        </div>
                        <div>
                            <h3 className="text-lg font-black text-slate-900 uppercase tracking-tight">Export Chatbot</h3>
                            <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">Deploy your bot to any website or app</p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-slate-100 rounded-full transition-colors group"
                    >
                        <X size={20} className="text-slate-400 group-hover:text-slate-900" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
                    <div className="space-y-8">
                        {/* Tab Switcher */}
                        <div className="flex p-1.5 bg-slate-50 rounded-2xl gap-1 border border-slate-200/50 shadow-inner">
                            {[
                                { id: "html", label: "HTML Snippet", icon: Code },
                                { id: "react", label: "React / TS", icon: Terminal },
                                { id: "nextjs", label: "Next.js", icon: Layers },
                            ].map((tab) => (
                                <button
                                    key={tab.id}
                                    onClick={() => setActiveTab(tab.id as any)}
                                    className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${activeTab === tab.id
                                        ? "bg-white text-blue-600 shadow-md border border-slate-200"
                                        : "text-slate-400 hover:text-slate-600 hover:bg-white/50"
                                        }`}
                                >
                                    <tab.icon size={14} strokeWidth={2.5} />
                                    {tab.label}
                                </button>
                            ))}
                        </div>

                        {/* Code Display */}
                        <div className="space-y-4">
                            <div className="flex items-center justify-between mb-2">
                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                                    {activeTab.toUpperCase()} Integration Code
                                </p>
                                <button
                                    onClick={() => handleCopy(activeTab, snippets[activeTab])}
                                    className="flex items-center gap-2 px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-[10px] font-bold hover:bg-slate-50 transition-all text-slate-600 hover:text-slate-900 shadow-sm"
                                >
                                    {copied === activeTab ? (
                                        <>
                                            <Check size={12} className="text-green-500" />
                                            Copied!
                                        </>
                                    ) : (
                                        <>
                                            <Copy size={12} />
                                            Copy Code
                                        </>
                                    )}
                                </button>
                            </div>
                            <div className="bg-slate-50 border border-slate-200 rounded-2xl p-8 font-mono text-sm group relative overflow-hidden min-h-[300px] flex flex-col justify-center shadow-inner">
                                {checkingStatus ? (
                                    <div className="flex flex-col items-center justify-center space-y-6 text-center">
                                        <div className="w-12 h-12 border-4 border-blue-100 border-t-blue-600 rounded-full animate-spin shadow-inner" />
                                        <div className="space-y-2">
                                            <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Checking Bot Status</h4>
                                            <p className="text-[10px] text-slate-400 font-bold uppercase tracking-tighter italic">Verifying your active plan...</p>
                                        </div>
                                    </div>
                                ) : isUnlocked ? (
                                    <motion.div
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                    >
                                        <pre className="text-slate-700 overflow-x-auto whitespace-pre-wrap leading-relaxed selection:bg-blue-100 italic">
                                            {snippets[activeTab]}
                                        </pre>
                                        <div className="absolute top-0 right-0 w-1/4 h-full bg-gradient-to-l from-slate-100/0 to-transparent pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity" />
                                    </motion.div>
                                ) : (
                                    <AnimatePresence mode="wait">
                                        {!exporting ? (
                                            <motion.div
                                                key="locked"
                                                initial={{ opacity: 0, scale: 0.95 }}
                                                animate={{ opacity: 1, scale: 1 }}
                                                exit={{ opacity: 0, scale: 1.05 }}
                                                className="flex flex-col items-center justify-center space-y-6 text-center"
                                            >
                                                <div className="relative">
                                                    <div className="p-5 bg-blue-50 rounded-full border border-blue-100 relative z-10 shadow-inner">
                                                        <Lock size={32} className="text-blue-600" />
                                                    </div>
                                                    <motion.div
                                                        animate={{ scale: [1, 1.2, 1] }}
                                                        transition={{ duration: 2, repeat: Infinity }}
                                                        className="absolute inset-0 bg-blue-400/10 rounded-full blur-xl -z-0"
                                                    />
                                                </div>

                                                <div className="space-y-2">
                                                    <h4 className="text-xl font-black text-slate-900 tracking-tight uppercase">Active Plan Required</h4>
                                                    <p className="text-[11px] text-slate-500 max-w-[280px] leading-relaxed mx-auto font-medium">
                                                        This chatbot needs an active subscription plan to unlock export features and production deployment.
                                                    </p>
                                                </div>

                                                <div className="flex items-center gap-6 py-2">
                                                    <div className="flex flex-col items-center gap-1">
                                                        <ShieldCheck size={16} className="text-blue-600/30" />
                                                        <span className="text-[10px] text-slate-400 uppercase font-black tracking-widest">Secure</span>
                                                    </div>
                                                    <div className="h-8 w-px bg-slate-200" />
                                                    <div className="flex flex-col items-center gap-1">
                                                        <Zap size={16} className="text-blue-600/30" />
                                                        <span className="text-[10px] text-slate-400 uppercase font-black tracking-widest">Unlocked</span>
                                                    </div>
                                                </div>

                                                <button
                                                    onClick={() => window.location.href = "/dashboard/billing"}
                                                    className="group relative px-10 py-4 bg-blue-600 hover:bg-blue-700 text-white rounded-2xl text-xs font-black uppercase tracking-widest transition-all shadow-xl shadow-blue-500/20 active:scale-95 overflow-hidden"
                                                >
                                                    <div className="relative z-10 flex items-center gap-2">
                                                        Get Active Plan
                                                    </div>
                                                    <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000" />
                                                </button>
                                            </motion.div>
                                        ) : (
                                            <motion.div
                                                key="exporting"
                                                initial={{ opacity: 0 }}
                                                animate={{ opacity: 1 }}
                                                exit={{ opacity: 0 }}
                                                className="flex flex-col items-center justify-center space-y-6 text-center"
                                            >
                                                <div className="w-16 h-16 border-4 border-blue-100 border-t-blue-600 rounded-full animate-spin shadow-inner" />
                                                <div className="space-y-2">
                                                    <h4 className="text-xs font-black text-slate-900 uppercase tracking-widest">Processing Export</h4>
                                                    <p className="text-[10px] text-slate-400 font-bold uppercase tracking-tighter">Preparing your deployment code...</p>
                                                </div>
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                )}
                            </div>
                        </div>

                        {/* Instructions */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4">
                            <div className="p-5 bg-slate-50 rounded-2xl border border-slate-200 space-y-3 shadow-inner">
                                <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-wider">Quick Setup</h4>
                                <ul className="space-y-2">
                                    {[
                                        "Copy the code snippet above",
                                        "Paste it before the closing </body> tag",
                                        "Refresh your website to see the bot"
                                    ].map((step, i) => (
                                        <li key={i} className="text-[11px] text-slate-500 flex gap-2 font-medium">
                                            <span className="text-blue-600 font-black">{i + 1}.</span> {step}
                                        </li>
                                    ))}
                                </ul>
                            </div>
                            <div className="p-5 bg-blue-50 rounded-2xl border border-blue-100 space-y-3 shadow-inner">
                                <h4 className="text-[10px] font-black text-blue-600/60 uppercase tracking-wider">Need Help?</h4>
                                <p className="text-[11px] text-slate-500 leading-relaxed font-medium">
                                    If you are having trouble deploying, check our documentation or reach out to support. Your Bot ID is:
                                </p>
                                <code className="block p-2 bg-white/50 border border-white rounded-lg text-[10px] text-blue-600 font-mono text-center font-bold">
                                    {botId}
                                </code>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="p-6 bg-slate-50 border-t border-slate-100 flex items-center justify-between">
                    <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">
                        Generated by Nimmi AI Engine • v1.0.4
                    </p>
                    <button
                        onClick={onClose}
                        className="px-6 py-2.5 bg-white hover:bg-slate-50 border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all shadow-sm"
                    >
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
}

