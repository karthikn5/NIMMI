"use client";

import { useEffect, useState, useRef } from "react";
import { MessageSquare, User, Clock, Check, Send, ArrowLeft, ShieldAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { io } from "socket.io-client";
import { motion, AnimatePresence } from "framer-motion";

export default function LiveChat() {
    const [handoffs, setHandoffs] = useState<any[]>([]);
    const [selectedChat, setSelectedChat] = useState<any>(null);
    const [messages, setMessages] = useState<any[]>([]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(true);
    const [unreadCounts, setUnreadCounts] = useState<Record<string, number>>({});
    const socketRef = useRef<any>(null);
    const router = useRouter();

    const apiUrl = typeof window !== "undefined" && (window.location.hostname.includes("nimmiai.in") || window.location.hostname.includes("railway.app"))
        ? "https://api.nimmiai.in"
        : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");

    const selectedChatRef = useRef<any>(null);
    useEffect(() => {
        selectedChatRef.current = selectedChat;
    }, [selectedChat]);

    useEffect(() => {
        const userId = localStorage.getItem("nimmi_user_id");
        if (!userId) {
            router.push("/auth/signup");
            return;
        }

        // Initialize Socket.io
        const socket = io(apiUrl, {
            transports: ["websocket"],
            upgrade: false
        });
        socketRef.current = socket;

        socket.on("connect", () => {
            console.log("Connected to WebSocket");
            // Join admin room
            socket.emit("join", { room: `admin_${userId}` });
        });

        socket.on("handoff_requested", (data: any) => {
            console.log("New handoff requested:", data);
            fetchHandoffs();
        });

        socket.on("message", (data: any) => {
            console.log("DEBUG: Socket message received:", data);
            
            // Increment unread count if it's not the selected chat and it's from a visitor
            if (data.sender === 'visitor' || data.sender === 'user') {
                if (!selectedChatRef.current || (data.room !== selectedChatRef.current.session_id)) {
                    setUnreadCounts(prev => ({
                        ...prev,
                        [data.room]: (prev[data.room] || 0) + 1
                    }));
                }
            }

            // If the message is for the currently selected chat
            if (selectedChatRef.current && (data.room === selectedChatRef.current.session_id)) {
                setMessages(prev => {
                    // Map sender 'visitor' or 'user' to 'user' for UI display
                    const displaySender = (data.sender === 'visitor' || data.sender === 'user') ? 'user' : 'agent';
                    
                    return [...prev, {
                        text: data.message,
                        sender: displaySender,
                        timestamp: new Date()
                    }];
                });
            }
        });

        fetchHandoffs();

        return () => {
            socket.disconnect();
        };
    }, [router]);

    const fetchHandoffs = async () => {
        // Set a safety timeout to stop loading spinner after 5 seconds no matter what
        const timeout = setTimeout(() => setLoading(false), 5000);
        
        try {
            const res = await fetch(`${apiUrl}/api/handoffs/pending`);
            if (res.ok) {
                const data = await res.json();
                // Filter for human sessions only to avoid duplicates from AI mode
                const humanHandoffs = data.filter((h: any) => 
                    h.session_id.startsWith('widget-session-human-')
                );
                setHandoffs(humanHandoffs);
            }
        } catch (err) {
            console.error("Failed to fetch handoffs:", err);
        } finally {
            clearTimeout(timeout);
            setLoading(false);
        }
    };

    const handleAccept = async (handoff: any) => {
        const userId = localStorage.getItem("nimmi_user_id");
        try {
            const res = await fetch(`${apiUrl}/api/handoffs/${handoff.conversation_id}/accept?agent_id=${userId}`, {
                method: "POST"
            });
            if (res.ok) {
                setSelectedChat(handoff);
                // Reset unread count for this session
                setUnreadCounts(prev => ({
                    ...prev,
                    [handoff.session_id]: 0
                }));
                
                // Fetch previous conversation history
                try {
                    const msgsRes = await fetch(`${apiUrl}/api/handoffs/${handoff.conversation_id}/messages`);
                    if (msgsRes.ok) {
                        const history = await msgsRes.json();
                        const formattedHistory = history.map((m: any) => ({
                            text: m.content,
                            sender: m.role === "user" ? "user" : "agent", // bot messages mapped to agent side temporarily or could be separate
                            timestamp: new Date(m.timestamp)
                        }));
                        setMessages([
                            ...formattedHistory,
                            {
                                text: "SYSTEM: You have joined the conversation.",
                                sender: "system",
                                timestamp: new Date()
                            }
                        ]);
                    } else {
                        setMessages([{
                            text: "SYSTEM: You have joined the conversation.",
                            sender: "system",
                            timestamp: new Date()
                        }]);
                    }
                } catch (e) {
                    setMessages([{
                        text: "SYSTEM: You have joined the conversation.",
                        sender: "system",
                        timestamp: new Date()
                    }]);
                }
                
                // Join the visitor's room
                socketRef.current.emit("join", { room: handoff.session_id });
            }
        } catch (err) {
            console.error("Failed to accept handoff:", err);
        }
    };

    const sendMessage = () => {
        if (!input.trim() || !selectedChat) return;

        const data = {
            room: selectedChat.session_id,
            message: input,
            sender: "agent"
        };

        socketRef.current.emit("message", data);
        setInput("");
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-[#faf9f7]">
                <div className="w-12 h-12 border-4 border-[#9d55ac]/10 border-t-[#9d55ac] rounded-full animate-spin" />
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[#faf9f7] flex flex-col">
            {/* Header */}
            <header className="bg-white border-b border-zinc-200 px-8 py-6 flex items-center justify-between shadow-sm">
                <div className="flex items-center gap-4">
                    <button onClick={() => router.push("/dashboard")} className="p-2 hover:bg-zinc-50 rounded-xl transition-colors">
                        <ArrowLeft size={20} className="text-zinc-400" />
                    </button>
                    <div>
                        <h1 className="text-xl font-black text-zinc-900 uppercase tracking-tight">Live Chat Agent</h1>
                        <p className="text-[10px] text-zinc-400 font-bold uppercase tracking-widest">Human-in-the-loop takeover</p>
                    </div>
                </div>
                <div className="flex items-center gap-2 px-4 py-2 bg-green-50 text-green-600 rounded-full border border-green-100">
                    <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                    <span className="text-[10px] font-black uppercase tracking-widest">Agent Online</span>
                </div>
            </header>

            <main className="flex-grow flex overflow-hidden">
                {/* Sidebar: Pending Handoffs */}
                <div className="w-96 border-r border-zinc-200 bg-white flex flex-col">
                    <div className="p-6 border-b border-zinc-100 flex items-center justify-between">
                        <h2 className="text-sm font-black text-zinc-400 uppercase tracking-widest">Pending Requests ({handoffs.length})</h2>
                        {Object.values(unreadCounts).reduce((a, b) => a + b, 0) > 0 && (
                            <motion.div 
                                initial={{ scale: 0 }}
                                animate={{ scale: 1 }}
                                className="bg-red-500 text-white text-[10px] font-black px-2 py-0.5 rounded-full shadow-lg shadow-red-500/20 animate-pulse"
                            >
                                {Object.values(unreadCounts).reduce((a, b) => a + b, 0)} NEW
                            </motion.div>
                        )}
                    </div>
                    <div className="flex-grow overflow-y-auto p-4 space-y-4">
                        <AnimatePresence>
                            {handoffs.map((handoff) => (
                                <motion.div
                                    key={handoff.conversation_id}
                                    initial={{ opacity: 0, x: -20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    exit={{ opacity: 0, x: -20 }}
                                    onClick={() => handleAccept(handoff)}
                                    className={`p-6 rounded-3xl border cursor-pointer transition-all ${
                                        selectedChat?.conversation_id === handoff.conversation_id
                                            ? "bg-zinc-900 border-zinc-900 shadow-xl shadow-zinc-900/20"
                                            : "bg-white border-zinc-100 hover:border-[#9d55ac] hover:shadow-lg"
                                    }`}
                                >
                                    <div className="flex justify-between items-start mb-4">
                                        <div className="relative">
                                            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                                                selectedChat?.conversation_id === handoff.conversation_id ? "bg-white/10" : "bg-purple-50"
                                            }`}>
                                                <User size={20} className={selectedChat?.conversation_id === handoff.conversation_id ? "text-white" : "text-[#9d55ac]"} />
                                            </div>
                                            {unreadCounts[handoff.session_id] > 0 && (
                                                <motion.div 
                                                    initial={{ scale: 0 }}
                                                    animate={{ scale: 1 }}
                                                    className="absolute -top-1 -right-1 bg-red-500 text-white text-[8px] font-black w-4 h-4 rounded-full flex items-center justify-center border border-white animate-pulse"
                                                >
                                                    {unreadCounts[handoff.session_id]}
                                                </motion.div>
                                            )}
                                        </div>
                                        <span className={`text-[9px] font-black uppercase tracking-widest ${
                                            selectedChat?.conversation_id === handoff.conversation_id ? "text-zinc-500" : "text-zinc-300"
                                        }`}>
                                            {new Date(handoff.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                        </span>
                                    </div>
                                    <h3 className={`text-sm font-bold mb-1 ${
                                        selectedChat?.conversation_id === handoff.conversation_id ? "text-white" : "text-zinc-900"
                                    }`}>{handoff.bot_name}</h3>
                                    <p className={`text-[10px] font-medium truncate ${
                                        selectedChat?.conversation_id === handoff.conversation_id ? "text-zinc-400" : "text-zinc-500"
                                    }`}>
                                        ID: {handoff.session_id.slice(0, 12)}...
                                    </p>
                                </motion.div>
                            ))}
                        </AnimatePresence>
                        {handoffs.length === 0 && (
                            <div className="text-center py-20">
                                <ShieldAlert size={40} className="text-zinc-200 mx-auto mb-4" />
                                <p className="text-xs font-bold text-zinc-400 uppercase tracking-widest">No pending handoffs</p>
                            </div>
                        )}
                    </div>
                </div>

                {/* Chat Area */}
                <div className="flex-grow flex flex-col bg-[#faf9f7]">
                    {selectedChat ? (
                        <>
                            {/* Chat Header */}
                            <div className="bg-white border-b border-zinc-100 p-6 flex items-center justify-between">
                                <div className="flex items-center gap-4">
                                    <div className="w-12 h-12 bg-zinc-900 rounded-2xl flex items-center justify-center text-white">
                                        <MessageSquare size={24} />
                                    </div>
                                    <div>
                                        <h3 className="text-sm font-bold text-zinc-900">{selectedChat.bot_name} - Live Session</h3>
                                        <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">Active with Visitor {selectedChat.session_id.slice(0, 8)}</p>
                                    </div>
                                </div>
                                <button className="px-4 py-2 bg-zinc-50 text-zinc-400 rounded-xl hover:text-red-500 transition-colors">
                                    <Check size={18} />
                                </button>
                            </div>

                            {/* Messages */}
                            <div className="flex-grow overflow-y-auto p-8 space-y-6">
                                {messages.map((msg, i) => (
                                    <div key={i} className={`flex ${msg.sender === 'agent' ? 'justify-end' : 'justify-start'}`}>
                                        <div className={`max-w-[70%] p-5 rounded-[2rem] text-sm font-medium shadow-sm ${
                                            msg.sender === 'agent' 
                                                ? "bg-zinc-900 text-white rounded-tr-none" 
                                                : msg.sender === 'system'
                                                    ? "bg-zinc-100 text-zinc-400 text-[10px] uppercase tracking-widest font-black text-center w-full"
                                                    : "bg-white text-zinc-900 rounded-tl-none border border-zinc-100"
                                        }`}>
                                            {msg.text}
                                        </div>
                                    </div>
                                ))}
                            </div>

                            {/* Input */}
                            <div className="p-8">
                                <div className="max-w-4xl mx-auto relative">
                                    <input
                                        type="text"
                                        value={input}
                                        onChange={(e) => setInput(e.target.value)}
                                        onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
                                        placeholder="Type a message to the visitor..."
                                        className="w-full bg-white border border-zinc-200 rounded-[2.5rem] pl-8 pr-20 py-6 text-sm font-medium focus:border-[#9d55ac] focus:ring-4 focus:ring-[#9d55ac]/5 outline-none shadow-xl shadow-zinc-900/5 transition-all"
                                    />
                                    <button
                                        onClick={sendMessage}
                                        className="absolute right-3 top-1/2 -translate-y-1/2 w-14 h-14 bg-zinc-900 text-white rounded-full flex items-center justify-center hover:scale-105 active:scale-95 transition-all shadow-lg"
                                    >
                                        <Send size={20} />
                                    </button>
                                </div>
                            </div>
                        </>
                    ) : (
                        <div className="flex-grow flex flex-col items-center justify-center">
                            <div className="w-24 h-24 bg-white rounded-[2rem] shadow-xl flex items-center justify-center mb-8 border border-zinc-100">
                                <MessageSquare size={40} className="text-zinc-200" />
                            </div>
                            <h2 className="text-xl font-bold text-zinc-900 mb-2">Select a conversation</h2>
                            <p className="text-zinc-400 text-sm font-medium">Pick a pending request from the left to start chatting.</p>
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}
