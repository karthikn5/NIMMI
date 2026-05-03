"use client";

import { use, useEffect, useState, useRef, Suspense } from "react";
import { Send, User, Bot, X, Maximize2, Minimize2, Paperclip, Smile } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";

interface Message {
    id: string;
    text: string;
    sender: "user" | "bot";
    timestamp: Date;
}

function WidgetContent({ params }: { params: Promise<{ botId: string }> }) {
    const { botId } = use(params);
    const searchParams = useSearchParams();
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [botConfig, setBotConfig] = useState<any>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const apiBase = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
        ? 'http://localhost:8000'
        : 'https://api.nimmiai.in';

    useEffect(() => {
        const fetchConfig = async () => {
            try {
                const res = await fetch(`${apiBase}/api/bots/${botId}/config`);
                if (res.ok) {
                    const data = await res.json();
                    setBotConfig(data);
                    
                    // Add welcome message if configured
                    setMessages([{
                        id: 'welcome',
                        text: `Hi! I'm ${data.bot_name || 'Assistant'}. How can I help you today?`,
                        sender: 'bot',
                        timestamp: new Date()
                    }]);
                }
            } catch (err) {
                console.error("Failed to load bot config:", err);
            }
        };
        fetchConfig();
    }, [botId, apiBase]);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    const handleSend = async () => {
        if (!input.trim() || loading) return;

        const userMsg: Message = {
            id: Date.now().toString(),
            text: input,
            sender: "user",
            timestamp: new Date()
        };

        setMessages(prev => [...prev, userMsg]);
        setInput("");
        setLoading(true);

        const isDemo = searchParams.get('is_demo') === 'true';
        
        try {
            const res = await fetch(`${apiBase}/api/chat/message/stream`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    bot_id: botId,
                    message: input,
                    visitor_session_id: "widget-session-" + botId,
                    history: messages.map(m => ({ role: m.sender === 'user' ? 'user' : 'assistant', content: m.text })),
                    is_demo: isDemo
                })
            });

            if (!res.ok) throw new Error("Failed to get response");

            const botMsgId = (Date.now() + 1).toString();
            setMessages(prev => [...prev, { id: botMsgId, text: "", sender: "bot", timestamp: new Date() }]);

            const reader = res.body?.getReader();
            const decoder = new TextDecoder();
            let accumulatedText = "";

            if (reader) {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value);
                    const lines = chunk.split("\n");
                    
                    for (const line of lines) {
                        if (line.startsWith("data: ")) {
                            const data = line.slice(6);
                            if (data === "[DONE]") break;
                            accumulatedText += data;
                            setMessages(prev => prev.map(m => m.id === botMsgId ? { ...m, text: accumulatedText } : m));
                        }
                    }
                }
            }
        } catch (err) {
            console.error("Chat error:", err);
            setMessages(prev => [...prev, {
                id: 'error',
                text: "I'm sorry, I encountered an error. Please try again.",
                sender: 'bot',
                timestamp: new Date()
            }]);
        } finally {
            setLoading(false);
        }
    };

    const visual = botConfig?.visual_config || {};
    const primaryColor = visual.color || "#9d55ac";
    const fontFamily = visual.font_family || visual.fontFamily || "Inter, sans-serif";
    const headerHeight = visual.header_height ? `${visual.header_height}px` : (visual.headerHeight ? `${visual.headerHeight}px` : "auto");
    const borderRadius = visual.border_radius ? `${visual.border_radius}px` : (visual.borderRadius ? `${visual.borderRadius}px` : "24px");
    const chatBg = visual.chat_bg_color || visual.chatBgColor || "#f8fafc";
    
    const googleFontName = fontFamily.replace(/'/g, "").split(",")[0].replace(/ /g, "+");
    const fontUrl = `https://fonts.googleapis.com/css2?family=${googleFontName}:wght@400;700&display=swap`;
    
    return (
        <div 
            className="flex flex-col h-screen overflow-hidden relative" 
            style={{ 
                fontFamily,
                backgroundColor: chatBg,
            }}
        >
            {(visual.background_image || visual.backgroundImage) && (
                <div
                    className="absolute inset-0 z-0 pointer-events-none"
                    style={{
                        backgroundImage: `url(${(visual.background_image || visual.backgroundImage).includes('/static/uploads/') ? `${apiBase}/static/uploads/${(visual.background_image || visual.backgroundImage).split('/').pop()}` : (visual.background_image || visual.backgroundImage)})`,
                        backgroundSize: 'cover',
                        backgroundPosition: 'center',
                        opacity: visual.background_opacity ?? visual.backgroundOpacity ?? 1
                    }}
                />
            )}
            {/* Header - Exact Builder Match */}
            <header 
                className="p-6 font-bold flex items-center justify-between shrink-0 shadow-lg relative z-10" 
                style={{ 
                    backgroundColor: primaryColor,
                    color: visual.text_color || visual.textColor || "#ffffff",
                    height: headerHeight !== "auto" ? headerHeight : "auto"
                }}
            >
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center overflow-hidden backdrop-blur-md border border-white/10">
                        {(() => {
                            let logoUrl = visual.logo_url || visual.botLogo;
                            if (logoUrl && logoUrl.includes('/static/uploads/')) {
                                const fileName = logoUrl.split('/').pop();
                                logoUrl = `${apiBase}/static/uploads/${fileName}`;
                            }
                            return logoUrl ? (
                                <img 
                                    src={logoUrl} 
                                    alt="Logo" 
                                    className="w-full h-full object-cover" 
                                    onError={(e) => {
                                        const img = e.target as HTMLImageElement;
                                        img.style.display = 'none';
                                        const parent = img.parentElement;
                                        if (parent && !parent.querySelector('.fallback-icon')) {
                                            const div = document.createElement('div');
                                            div.className = 'fallback-icon flex items-center justify-center w-full h-full bg-[#9d55ac] text-white text-[10px] font-black uppercase';
                                            div.innerText = 'Bot';
                                            parent.appendChild(div);
                                        }
                                    }}
                                />
                            ) : (
                                <div className="flex items-center justify-center w-full h-full bg-[#9d55ac] text-white text-[10px] font-black uppercase">
                                    Bot
                                </div>
                            );
                        })()}
                    </div>
                    <span className="drop-shadow-sm text-base tracking-tight">{botConfig?.bot_name || "Nimmi Assistant"}</span>
                </div>
                <button onClick={() => window.parent.postMessage('close-nimmi-widget', '*')} className="p-1.5 hover:bg-white/10 rounded-lg transition-colors opacity-80 hover:opacity-100" style={{ color: visual.text_color || visual.textColor || "#ffffff" }}>
                    <X size={20} />
                </button>
            </header>

            {/* Messages */}
            <main className="flex-1 overflow-y-auto p-6 space-y-4 custom-scrollbar relative z-10">
                <AnimatePresence initial={false}>
                    {messages.map((msg) => (
                        <motion.div
                            key={msg.id}
                            initial={{ opacity: 0, y: 10, scale: 0.98 }}
                            animate={{ opacity: 1, y: 0, scale: 1 }}
                            className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"} items-start gap-2`}
                        >
                            {msg.sender === "bot" && (
                                <div className="w-7 h-7 rounded-full flex items-center justify-center text-white shrink-0 mt-1" style={{ backgroundColor: primaryColor }}>
                                    <Bot size={14} />
                                </div>
                            )}
                            <div
                                className={`p-4 text-xs leading-relaxed max-w-[85%] shadow-sm border border-slate-100 ${msg.sender === "user" ? "shadow-md transition-transform hover:scale-[1.02]" : ""}`}
                                style={{
                                    borderRadius: borderRadius,
                                    backgroundColor: msg.sender === "user" ? (visual.user_bubble_bg || visual.userBubbleBg || primaryColor) : (visual.assistant_bubble_bg || visual.assistantBubbleBg || "#E5E7EB"),
                                    color: msg.sender === "user" ? (visual.user_bubble_text || visual.userBubbleText || "#ffffff") : (visual.assistant_bubble_text || visual.assistantBubbleText || "#1F2937"),
                                    borderTopRightRadius: msg.sender === "user" ? 0 : undefined,
                                    borderTopLeftRadius: msg.sender === "bot" ? 0 : undefined,
                                }}
                            >
                                {msg.text || (loading && msg.sender === 'bot' ? <span className="flex gap-1 animate-pulse"><span className="w-1 h-1 bg-slate-400 rounded-full"/><span className="w-1 h-1 bg-slate-400 rounded-full"/><span className="w-1 h-1 bg-slate-400 rounded-full"/></span> : "")}
                            </div>
                        </motion.div>
                    ))}
                </AnimatePresence>
                <div ref={messagesEndRef} />
            </main>

            {/* Input - Rectangular Style Match */}
            <footer className="p-4 bg-zinc-900/80 border-t border-white/5 flex gap-2 backdrop-blur-md relative z-10">
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyPress={(e) => e.key === "Enter" && handleSend()}
                    placeholder="Type a message..."
                    className="flex-1 rounded-xl border border-white/5 h-12 flex items-center px-4 text-sm shadow-inner outline-none"
                    style={{ backgroundColor: visual.input_bg_color || visual.inputBgColor || "#ffffff", color: visual.input_text_color || visual.inputTextColor || "#000000" }}
                />
                <button
                    onClick={handleSend}
                    disabled={!input.trim() || loading}
                    className="w-12 h-12 shrink-0 rounded-xl flex items-center justify-center shadow-lg active:scale-95 transition-all disabled:opacity-50"
                    style={{ backgroundColor: primaryColor, color: visual.text_color || visual.textColor || "#ffffff" }}
                >
                    <Send size={18} />
                </button>
            </footer>

            <style dangerouslySetInnerHTML={{ __html: `
                @import url('${fontUrl}');
                .custom-scrollbar::-webkit-scrollbar {
                    width: 4px;
                }
                .custom-scrollbar::-webkit-scrollbar-track {
                    background: transparent;
                }
                .custom-scrollbar::-webkit-scrollbar-thumb {
                    background: #e2e8f0;
                    border-radius: 10px;
                }
                .custom-scrollbar::-webkit-scrollbar-thumb:hover {
                    background: #cbd5e1;
                }
            `}} />
        </div>
    );
}

export default function WidgetPage({ params }: { params: Promise<{ botId: string }> }) {
    return (
        <Suspense fallback={<div className="flex h-screen items-center justify-center bg-white"><div className="w-8 h-8 border-4 border-slate-200 border-t-[#9d55ac] rounded-full animate-spin" /></div>}>
            <WidgetContent params={params} />
        </Suspense>
    );
}
