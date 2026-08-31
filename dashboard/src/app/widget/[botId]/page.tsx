"use client";

import { use, useEffect, useState, useRef, Suspense } from "react";
import { Send, User, Bot, X, Maximize2, Minimize2, Paperclip, Smile, Clock } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { io } from "socket.io-client";
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
    const [aiMessages, setAiMessages] = useState<Message[]>([]);
    const [humanMessages, setHumanMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [mode, setMode] = useState<"ai" | "human">("ai");
    const [botConfig, setBotConfig] = useState<any>(null);
    const [isHumanActive, setIsHumanActive] = useState(false);
    const socketRef = useRef<any>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Derived current messages based on mode
    const messages = mode === "ai" ? aiMessages : humanMessages;
    const setMessages = mode === "ai" ? setAiMessages : setHumanMessages;

    const handleModeToggle = async (newMode: "ai" | "human") => {
        if (newMode === mode) return;
        setMode(newMode);

        if (newMode === "human") {
            const humanSessionId = "widget-session-human-" + botId;
            try {
                const response = await fetch(`${apiBase}/api/chat/handoff`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        bot_id: botId,
                        visitor_session_id: humanSessionId
                    })
                });
                
                if (response.ok && humanMessages.length === 0) {
                    setHumanMessages([{
                        id: Date.now().toString(),
                        text: "Connecting with human... have notified a human agent. They will join the chat shortly.",
                        sender: "bot",
                        timestamp: new Date()
                    }]);
                }
                // Join the socket room immediately so messages are received
                if (socketRef.current) {
                    socketRef.current.emit("join", { room: humanSessionId });
                }
            } catch (err) {
                console.error("Handoff request failed:", err);
            }
        }
    };

    const apiBase = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
        ? 'http://localhost:8000'
        : 'https://api.nimmiai.in';

    useEffect(() => {
        // Initialize Socket.io
        const socket = io(apiBase, {
            transports: ["websocket"],
            upgrade: false
        });
        socketRef.current = socket;
        const humanSessionId = "widget-session-human-" + botId;

        socket.on("connect", () => {
            socket.emit("join", { room: humanSessionId });
        });

        socket.on("agent_joined", (data: any) => {
            setIsHumanActive(true);
            addHumanMessageSafely({
                id: `system-agent-joined-${Date.now()}`,
                text: "A human agent has joined the chat.",
                sender: 'bot',
                timestamp: new Date()
            });
        });

        socket.on("message", (data: any) => {
            if (data.sender === "agent") {
                addHumanMessageSafely({
                    id: Date.now().toString(),
                    text: data.message,
                    sender: 'bot',
                    timestamp: new Date()
                });
            }
        });

        return () => {
            socket.disconnect();
        };
    }, [botId, apiBase]);

    useEffect(() => {
        let hasHistory = false;
        const storageKey = `nimmi_chat_history_${botId}`;
        const savedData = localStorage.getItem(storageKey);
        
        if (savedData) {
            try {
                const { messages: savedMessages, timestamp, mode: savedMode } = JSON.parse(savedData);
                const now = Date.now();
                const twentyFourHours = 24 * 60 * 60 * 1000;
                
                if (now - timestamp < twentyFourHours && savedMode === "human") {
                    // Safety: Deduplicate messages by ID
                    const uniqueMessages = (savedMessages || []).filter((msg: any, index: number, self: any[]) =>
                        index === self.findIndex((m: any) => m.id === msg.id)
                    );
                    setHumanMessages(uniqueMessages.map((m: any) => ({
                        ...m,
                        timestamp: new Date(m.timestamp)
                    })));
                    setMode("human");
                    setIsHumanActive(true);
                    hasHistory = true;
                } else {
                    localStorage.removeItem(storageKey);
                }
            } catch (e) {
                console.error("Failed to parse chat history", e);
            }
        }

        const fetchConfig = async () => {
            try {
                const res = await fetch(`${apiBase}/api/bots/${botId}/config`);
                if (res.ok) {
                    const data = await res.json();
                    setBotConfig(data);
                    
                    // ALWAYS initialize AI chat with a welcome message
                    setAiMessages([{
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
        if (mode === "human" && humanMessages.length > 0) {
            const storageKey = `nimmi_chat_history_${botId}`;
            localStorage.setItem(storageKey, JSON.stringify({
                messages: humanMessages,
                timestamp: Date.now(),
                mode: "human"
            }));
        }
    }, [humanMessages, mode, botId]);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    // Helper to add messages with ID safety
    const addHumanMessageSafely = (newMsg: Message) => {
        setHumanMessages(prev => {
            if (prev.some(m => m.id === newMsg.id)) return prev;
            return [...prev, newMsg];
        });
    };

    const handleSend = async () => {
        if (!input.trim() || loading) return;

        const currentMode = mode;
        const currentInput = input;

        const userMsg: Message = {
            id: Date.now().toString(),
            text: currentInput,
            sender: "user",
            timestamp: new Date()
        };

        if (currentMode === "ai") setAiMessages(prev => [...prev, userMsg]);
        else setHumanMessages(prev => [...prev, userMsg]);
        
        setInput("");

        const sessionId = currentMode === "ai" 
            ? "widget-session-ai-" + botId 
            : "widget-session-human-" + botId;

        // If mode is human, ALWAYS send via WebSocket so messages are recorded in DB
        // and the admin is notified (whether agent has joined or is still pending).
        if (currentMode === "human") {
            if (socketRef.current?.connected) {
                socketRef.current.emit("message", {
                    room: sessionId,
                    message: currentInput,
                    sender: "visitor"
                });
            }
            return;
        }

        setLoading(true);
        const isDemo = searchParams.get('is_demo') === 'true';
        
        // Prepare history INCLUDING the message we just sent
        const updatedHistory = [...aiMessages, userMsg].map(m => ({ 
            role: m.sender === 'user' ? 'user' : 'assistant', 
            content: m.text 
        }));

        const botMsgId = (Date.now() + 1).toString();
        setAiMessages(prev => [...prev, { 
            id: botMsgId, 
            text: "", 
            sender: "bot", 
            timestamp: new Date() 
        }]);

        try {
            // Debug: Log that we are starting the request
            console.log("DEBUG: Starting fetch to", `${apiBase}/api/chat/message/stream`);
            
            const res = await fetch(`${apiBase}/api/chat/message/stream`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    bot_id: botId,
                    message: currentInput,
                    visitor_session_id: sessionId,
                    history: updatedHistory,
                    is_demo: isDemo
                })
            });

            if (!res.ok) throw new Error("Failed to get response");

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
                            setAiMessages(prev => prev.map(m => m.id === botMsgId ? { ...m, text: accumulatedText } : m));
                        }
                    }
                }
            }
        } catch (err: any) {
            console.error("Chat error:", err);
            const errorMessage = err.name === 'AbortError' 
                ? "The AI is taking a bit long to respond. Please try again in a moment."
                : "I'm sorry, I encountered an error. Please try again.";
                
            setAiMessages(prev => [...prev, {
                id: 'error',
                text: errorMessage,
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
            {/* Header - Perfected Alignment */}
            <header 
                className="p-4 font-bold flex items-center justify-between shrink-0 shadow-lg relative z-20 backdrop-blur-md rounded-t-2xl border-b border-white/10" 
                style={{ 
                    backgroundColor: primaryColor,
                    color: visual.text_color || visual.textColor || "#ffffff",
                }}
            >
                {/* Left: Identity */}
                <div className="flex items-center gap-3">
                    <div className="relative">
                        <img 
                            src={visual.logo_url || visual.botLogo || "https://img.freepik.com/free-vector/cyborg-concept-illustration_114360-155.jpg"} 
                            alt="bot" 
                            className="w-10 h-10 rounded-full border-2 border-white/50 object-cover shadow-lg"
                        />
                        <div className="absolute bottom-0 right-0 w-3 h-3 bg-green-500 rounded-full border-2 border-white animate-pulse"></div>
                    </div>
                    <div className="flex flex-col">
                        <span className="font-bold text-white text-sm tracking-tight truncate max-w-[80px]">
                            {botConfig?.bot_name || "Deepa"}
                        </span>
                        <div className="flex items-center gap-1">
                            <span className="w-1.5 h-1.5 bg-green-400 rounded-full"></span>
                            <p className="text-white/70 text-[8px] uppercase font-bold tracking-widest">Online</p>
                        </div>
                    </div>
                </div>

                {/* Right-aligned Group for Toggle and Close */}
                <div className="flex items-center gap-3 ml-auto">
                    {/* Mode Toggle */}
                    <div className="flex bg-black/20 p-1 rounded-full border border-white/10 shadow-inner scale-90">
                        <button 
                            onClick={() => handleModeToggle('ai')}
                            className={`px-3 py-1 rounded-full text-[9px] font-black uppercase transition-all duration-300 ${mode === 'ai' ? 'bg-white text-black shadow-md scale-105' : 'text-white/50 hover:text-white'}`}
                        >
                            AI
                        </button>
                        <button 
                            onClick={() => handleModeToggle('human')}
                            className={`px-3 py-1 rounded-full text-[9px] font-black uppercase transition-all duration-300 ${mode === 'human' ? 'bg-white text-black shadow-md scale-105' : 'text-white/50 hover:text-white'}`}
                        >
                            Human
                        </button>
                    </div>

                    {/* Close Button */}
                    <button 
                        onClick={() => window.parent.postMessage('close-nimmi-widget', '*')}
                        className="p-2 hover:bg-white/10 rounded-full text-white/70 hover:text-white transition-colors"
                    >
                        <X size={20} />
                    </button>
                </div>
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
                                <div className="w-7 h-7 rounded-full flex items-center justify-center text-white shrink-0 mt-1" style={{ backgroundColor: mode === "human" ? "#16a34a" : primaryColor }}>
                                    {mode === "human" ? <User size={14} /> : <Bot size={14} />}
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
            <footer className="p-4 bg-zinc-900/80 border-t border-white/5 flex flex-col gap-2 backdrop-blur-md relative z-10">
                {mode === "human" && (
                    <div className="text-[10px] text-white/40 flex items-center gap-1 mb-1 px-1">
                        <Clock size={10} />
                        <span>Chat history preserved for 24h</span>
                    </div>
                )}
                <div className="flex gap-2 w-full">
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
                </div>
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
