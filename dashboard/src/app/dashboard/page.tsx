"use client";

import { useEffect, useState } from "react";
import { Plus, Bot, ExternalLink, Settings, Trash2, Clock, Zap, ChevronRight, LayoutGrid, MessageSquare, PlusCircle, Sparkles, ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import NextImage from "next/image";

export default function Dashboard() {
    const [bots, setBots] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [creatingBot, setCreatingBot] = useState(false);
    const [userName, setUserName] = useState("");
    const [userEmail, setUserEmail] = useState("");
    const [usage, setUsage] = useState<any>(null);
    const router = useRouter();

    useEffect(() => {
        let userId = localStorage.getItem("nimmi_user_id");
        if (!userId) {
            router.push("/auth/signup");
            return;
        }
        userId = userId.trim();

        // ⚡ Speed Optimization: Load from cache first
        const cachedBots = localStorage.getItem(`bots_${userId}`);
        const cachedUsage = localStorage.getItem(`usage_${userId}`);
        if (cachedBots) setBots(JSON.parse(cachedBots));
        if (cachedUsage) setUsage(JSON.parse(cachedUsage));

        const fetchData = async () => {
            try {
                const apiUrl = typeof window !== "undefined" && (window.location.hostname.includes("nimmiai.in") || window.location.hostname.includes("railway.app"))
                    ? "https://api.nimmiai.in"
                    : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");

                const [profileRes, botsRes, usageRes] = await Promise.all([
                    fetch(`${apiUrl}/api/auth/profile?user_id=${userId}`),
                    fetch(`${apiUrl}/api/bots?user_id=${userId}`),
                    fetch(`${apiUrl}/api/usage?user_id=${userId}`)
                ]);

                if (profileRes.ok) {
                    const profileData = await profileRes.json();
                    setUserName(profileData.name || "User");
                    setUserEmail(profileData.email || "");
                }

                if (botsRes.ok) {
                    const botsData = await botsRes.json();
                    setBots(botsData);
                    localStorage.setItem(`bots_${userId}`, JSON.stringify(botsData));
                }

                if (usageRes.ok) {
                    const usageData = await usageRes.json();
                    setUsage(usageData);
                    localStorage.setItem(`usage_${userId}`, JSON.stringify(usageData));
                }
            } catch (err) {
                console.error("Dashboard data load error:", err);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [router]);

    const handleCreateBot = async () => {
        const userId = localStorage.getItem("nimmi_user_id");
        if (!userId) return;

        setCreatingBot(true);
        try {
            const apiUrl = typeof window !== "undefined" && window.location.hostname.includes("nimmiai.in")
                ? "https://api.nimmiai.in"
                : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");
            const res = await fetch(`${apiUrl}/api/bots/create`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: "My New Bot",
                    user_id: userId
                })
            });
            const data = await res.json();
            if (res.ok) {
                router.push(`/dashboard/builder/${data.id}`);
            } else {
                const errorMsg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
                alert(errorMsg || "Failed to create bot. Check your credit limit.");
            }
        } catch (err) {
            console.error("Failed to create bot:", err);
        } finally {
            setCreatingBot(false);
        }
    };

    const handleDeleteBot = async (botId: string, e: React.MouseEvent) => {
        e.stopPropagation();
        if (!confirm("Are you sure you want to delete this bot? This action cannot be undone.")) return;

        try {
            const apiUrl = typeof window !== "undefined" && window.location.hostname.includes("nimmiai.in")
                ? "https://api.nimmiai.in"
                : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");
            const res = await fetch(`${apiUrl}/api/bots/${botId}`, {
                method: "DELETE",
            });
            if (res.ok) {
                setBots(bots.filter(b => b.id !== botId));
                // Refresh usage to update credits
                const userId = localStorage.getItem("nimmi_user_id");
                const usageRes = await fetch(`${apiUrl}/api/usage?user_id=${userId}`);
                const usageData = await usageRes.json();
                if (usageRes.ok) setUsage(usageData);
            }
        } catch (err) {
            console.error("Failed to delete bot:", err);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-[#faf9f7]">
                <div className="w-12 h-12 border-4 border-[#9d55ac]/10 border-t-[#9d55ac] rounded-full animate-spin" />
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[#faf9f7] p-4 lg:p-10">
            <div className="max-w-7xl mx-auto">
                <header className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-12">
                    <div className="text-center md:text-left">
                        <motion.div
                            initial={{ opacity: 0, y: -20 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="inline-flex items-center gap-2 px-4 py-1.5 bg-purple-50 border border-purple-100 rounded-full mb-4"
                        >
                            <Sparkles size={14} className="text-[#9d55ac]" />
                            <span className="text-xs font-bold text-[#9d55ac] uppercase tracking-wider">Welcome back, {userName.split(' ')[0]}</span>
                        </motion.div>
                        <h1 className="text-4xl md:text-5xl font-bold text-zinc-900 mb-3 tracking-tight">
                            Your AI <span className="text-[#9d55ac]">Assistant Hub</span>
                        </h1>
                        <p className="text-zinc-500 font-medium">Manage, train, and deploy your custom AI chatbots.</p>
                    </div>

                    <button
                        onClick={handleCreateBot}
                        disabled={creatingBot}
                        className="bg-zinc-900 text-white px-8 py-4 rounded-[2rem] font-bold text-sm shadow-xl shadow-zinc-900/20 hover:bg-zinc-800 transition-all active:scale-95 flex items-center justify-center gap-2 group whitespace-nowrap"
                    >
                        <Plus size={20} className="group-hover:rotate-90 transition-transform duration-300" />
                        {creatingBot ? "Creating..." : "Create New Bot"}
                    </button>
                </header>

                {/* Quick Stats / Credits */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-12">
                    {/* Active Subscriptions Overview */}
                    <motion.div 
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.2 }}
                        onClick={() => router.push('/dashboard/billing')}
                        className="col-span-1 md:col-span-2 bg-white p-8 rounded-[2.5rem] border border-zinc-100 flex flex-col md:flex-row items-center gap-8 shadow-sm cursor-pointer hover:shadow-xl hover:shadow-purple-900/5 transition-all"
                    >
                        <div className="w-24 h-24 bg-[#9d55ac]/5 rounded-3xl flex items-center justify-center shrink-0 border border-[#9d55ac]/10 shadow-inner">
                            <Sparkles size={40} className="text-[#9d55ac]" />
                        </div>
                        <div className="flex-grow text-center md:text-left">
                            <h3 className="text-sm font-bold text-zinc-400 uppercase tracking-widest mb-1">Active Subscriptions</h3>
                            <div className="flex items-baseline justify-center md:justify-start gap-2 mb-2">
                                <span className="text-6xl font-bold text-zinc-900 tracking-tighter">
                                    {bots.filter(b => b.status === "Active").length}
                                </span>
                                <span className="text-zinc-400 font-bold text-xl">Managed Bots</span>
                            </div>
                            <p className="text-zinc-500 text-xs font-bold uppercase tracking-wider">
                                {bots.length} Total Bots Created
                            </p>
                        </div>
                        <button 
                            className="px-6 py-4 bg-zinc-900 text-white rounded-2xl font-bold text-xs uppercase tracking-widest hover:bg-zinc-800 transition-colors shrink-0 shadow-lg shadow-purple-900/10"
                        >
                            Manage Billing
                        </button>
                    </motion.div>

                    <motion.div 
                        whileHover={{ y: -5 }}
                        className="bg-zinc-900 p-8 rounded-[2.5rem] text-white shadow-2xl shadow-purple-900/10 relative overflow-hidden flex flex-col justify-between"
                    >
                        <div className="absolute top-0 right-0 p-6 opacity-[0.05]">
                            <Sparkles size={100} />
                        </div>
                        <div>
                            <h3 className="text-zinc-500 text-[10px] font-black uppercase tracking-[0.2em] mb-4">Pro Tip</h3>
                            <p className="text-lg font-bold leading-snug">Connect your website to train your AI instantly on all your pages.</p>
                        </div>
                        <div className="mt-8">
                            <button className="text-[#9d55ac] font-bold text-sm flex items-center gap-2 hover:gap-3 transition-all">
                                Read Guide <ChevronRight size={18} />
                            </button>
                        </div>
                    </motion.div>
                </div>

                {/* Bots Grid */}
                <div className="mb-20">
                    <div className="flex items-center gap-4 mb-8">
                        <div className="w-10 h-10 bg-white rounded-xl shadow-sm flex items-center justify-center border border-zinc-100">
                            <LayoutGrid size={18} className="text-[#9d55ac]" />
                        </div>
                        <h2 className="text-2xl font-bold text-zinc-900">Your Assistants</h2>
                        <div className="h-px bg-zinc-100 flex-grow" />
                        <span className="text-zinc-400 font-bold text-sm">{bots.length} Total</span>
                    </div>

                    {bots.length === 0 ? (
                        <motion.div 
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="bg-white border-2 border-dashed border-zinc-100 rounded-[3rem] p-16 text-center"
                        >
                            <div className="w-24 h-24 bg-zinc-50 rounded-full flex items-center justify-center mx-auto mb-8">
                                <Bot size={48} className="text-zinc-300" />
                            </div>
                            <h3 className="text-2xl font-bold text-zinc-900 mb-3">No bots built yet</h3>
                            <p className="text-zinc-500 max-w-sm mx-auto mb-10 font-medium">Create your first AI assistant and start training it on your custom data in minutes.</p>
                            <button
                                onClick={handleCreateBot}
                                className="inline-flex items-center gap-2 px-8 py-4 bg-[#9d55ac] text-white rounded-2xl font-bold text-sm shadow-xl shadow-purple-900/20 hover:scale-105 transition-all"
                            >
                                <PlusCircle size={20} /> Build My First Bot
                            </button>
                        </motion.div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                            <AnimatePresence>
                                {bots.map((bot, index) => (
                                    <motion.div
                                        key={bot.id}
                                        layout
                                        initial={{ opacity: 0, scale: 0.9 }}
                                        animate={{ opacity: 1, scale: 1 }}
                                        exit={{ opacity: 0, scale: 0.9 }}
                                        transition={{ delay: index * 0.05 }}
                                        onClick={() => router.push(`/dashboard/builder/${bot.id}`)}
                                        className="bg-white p-8 rounded-[2.5rem] shadow-[0_10px_30px_rgba(0,0,0,0.02)] border border-white hover:shadow-[0_20px_50px_rgba(0,0,0,0.05)] hover:-translate-y-2 transition-all cursor-pointer group relative overflow-hidden"
                                    >
                                        <div className="flex justify-between items-start mb-6">
                                            <div className="w-16 h-16 bg-purple-50 rounded-2xl flex items-center justify-center text-[#9d55ac] group-hover:scale-110 transition-transform">
                                                <MessageSquare size={32} />
                                            </div>
                                            <button
                                                onClick={(e) => handleDeleteBot(bot.id, e)}
                                                className="p-3 bg-zinc-50 text-zinc-400 rounded-xl hover:bg-red-50 hover:text-red-500 transition-colors"
                                            >
                                                <Trash2 size={16} />
                                            </button>
                                        </div>
                                        
                                        <h3 className="text-xl font-bold text-zinc-900 mb-1 group-hover:text-[#9d55ac] transition-colors">{bot.name}</h3>
                                        
                                        <div className="flex flex-col gap-1 mb-8">
                                            <div className="flex items-center gap-2 text-zinc-400 text-[10px] font-bold uppercase tracking-wider">
                                                <Zap size={10} className="text-amber-500" />
                                                Plan: <span className="text-zinc-600">{bot.plan || "No Plan"}</span>
                                            </div>
                                            <div className="flex items-center gap-2 text-zinc-400 text-[10px] font-bold uppercase tracking-wider">
                                                <Clock size={10} />
                                                Expiry: <span className="text-zinc-600">{bot.expiry || "-"}</span>
                                            </div>
                                        </div>

                                        <div className="flex items-center justify-between pt-6 border-t border-zinc-50">
                                            <div className="flex items-center gap-2">
                                                <span className={`w-2 h-2 rounded-full ${bot.status === 'Active' ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
                                                <span className={`text-[10px] font-bold uppercase tracking-widest ${bot.status === 'Active' ? 'text-green-600' : 'text-red-500'}`}>
                                                    {bot.status}
                                                </span>
                                            </div>
                                            <div className="flex gap-2">
                                                {bot.days_remaining > 0 && (
                                                    <span className="text-[10px] font-black text-zinc-300 uppercase mr-2">
                                                        {bot.days_remaining} Days Left
                                                    </span>
                                                )}
                                                <div className="p-2 bg-zinc-50 rounded-lg text-zinc-400 hover:text-[#9d55ac] transition-colors">
                                                    <Settings size={14} />
                                                </div>
                                            </div>
                                        </div>
                                    </motion.div>
                                ))}
                            </AnimatePresence>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
