"use client";

import { Bot, Plus, Settings, BarChart2, LayoutDashboard, Database, User, MessageSquare, LogOut, ChevronUp, Crown } from "lucide-react";
import Link from "next/link";
import Image from "next/image";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";

export default function Dashboard() {
    const [bots, setBots] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [userName, setUserName] = useState("");
    const [userEmail, setUserEmail] = useState("");
    const [showProfileMenu, setShowProfileMenu] = useState(false);
    const [creatingBot, setCreatingBot] = useState(false);
    const [isSidebarOpen, setIsSidebarOpen] = useState(false); // Mobile menu state
    const router = useRouter();

    useEffect(() => {
        const userId = localStorage.getItem("nimmi_user_id");
        const storedName = localStorage.getItem("nimmi_user_name");
        const storedEmail = localStorage.getItem("nimmi_user_email");

        if (!userId) {
            router.push("/auth/signup");
            return;
        }

        setUserName(storedName || "User");
        if (storedEmail) setUserEmail(storedEmail);

        // Fetch user profile
        const fetchProfile = async () => {
            try {
                const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/auth/profile?user_id=${userId}`);
                const data = await res.json();
                if (res.ok) {
                    setUserName(data.name || "User");
                    setUserEmail(data.email || "");
                }
            } catch (err) {
                console.error("Failed to fetch profile:", err);
            }
        };

        const fetchBots = async () => {
            try {
                const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/bots?user_id=${userId}`);
                const data = await res.json();
                setBots(data);
            } catch (err) {
                console.error("Failed to fetch bots:", err);
            } finally {
                setLoading(false);
            }
        };

        fetchProfile();
        fetchBots();
    }, [router]);

    const handleCreateBot = async () => {
        const userId = localStorage.getItem("nimmi_user_id");
        if (!userId) return;

        setCreatingBot(true);
        try {
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/bots/create`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    user_id: userId,
                    bot_name: "New AI Bot",
                    system_prompt: "You are a helpful assistant.",
                    visual_config: { color: "#3b82f6", logo_url: "", position: "right" }
                })
            });
            const data = await res.json();
            if (res.ok) {
                router.push(`/dashboard/builder/${data.bot_id}`);
            } else {
                setCreatingBot(false);
                alert("Failed to create bot: " + (data.detail || "Unknown error"));
            }
        } catch (err) {
            console.error("Failed to create bot:", err);
            setCreatingBot(false);
            alert("Error creating bot. Please try again.");
        }
    };


    const handleDeleteBot = async (botId: string, botName: string, e: React.MouseEvent) => {
        e.stopPropagation(); // Prevent navigation to builder
        if (!confirm(`Are you sure you want to delete "${botName}"? This action cannot be undone.`)) {
            return;
        }

        try {
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/bots/${botId}`, {
                method: "DELETE",
            });

            if (res.ok) {
                setBots(bots.filter(bot => bot.id !== botId));
            } else {
                alert("Failed to delete bot");
            }
        } catch (err) {
            console.error("Failed to delete bot:", err);
            alert("Error deleting bot");
        }
    };

    const handleLogout = () => {
        localStorage.removeItem("nimmi_user_id");
        localStorage.removeItem("nimmi_user_name");
        router.push("/auth/login");
    };

    return (
        <div className="flex min-h-screen bg-[#050505] text-white">
            {/* Mobile Header */}
            <header className="lg:hidden fixed top-0 left-0 right-0 h-16 bg-black/80 backdrop-blur-xl border-b border-white/5 flex items-center justify-between px-6 z-50">
                <div className="flex items-center gap-2 font-bold text-xl tracking-tight">
                    <div className="w-8 h-8 rounded-lg overflow-hidden flex items-center justify-center shadow-[0_0_15px_rgba(37,99,235,0.2)]">
                        <Image src="/nimmi-logo.png" alt="Nimmi AI" width={32} height={32} className="object-cover" />
                    </div>
                    Nimmi AI
                </div>
                <button 
                    onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                    className="p-2 hover:bg-white/5 rounded-lg transition-colors"
                >
                    <Plus className={`transition-transform duration-300 ${isSidebarOpen ? 'rotate-45' : ''}`} />
                </button>
            </header>

            {/* Sidebar */}
            <aside className={`
                fixed inset-y-0 left-0 z-40 w-72 bg-[#0a0a0a] border-r border-white/5 flex flex-col transition-transform duration-300 ease-in-out lg:static lg:translate-x-0
                ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'}
            `}>
                <div className="p-8 pb-4">
                    <div className="flex items-center gap-3 font-bold text-2xl tracking-tighter group cursor-default">
                        <div className="w-10 h-10 rounded-xl overflow-hidden flex items-center justify-center shadow-[0_0_20px_rgba(37,99,235,0.3)] group-hover:scale-105 transition-transform duration-300">
                            <Image src="/nimmi-logo.png" alt="Nimmi AI" width={40} height={40} className="object-cover" />
                        </div>
                        <span className="bg-gradient-to-r from-white to-white/60 bg-clip-text text-transparent">Nimmi AI</span>
                    </div>
                </div>

                <nav className="flex-1 px-4 py-8 flex flex-col gap-1.5 overflow-y-auto">
                    {[
                        { name: 'Dashboard', icon: LayoutDashboard, href: '/dashboard' },
                        { name: 'Analytics', icon: BarChart2, href: '#' },
                        { name: 'Knowledge Base', icon: Database, href: '#' },
                        { name: 'Profile Settings', icon: User, href: '/dashboard/profile' },
                    ].map((item) => {
                        const isActive = item.href === '/dashboard'; // Simple active state for now
                        return (
                            <Link 
                                key={item.name}
                                href={item.href} 
                                onClick={() => setIsSidebarOpen(false)}
                                className={`
                                    flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200
                                    ${isActive 
                                        ? 'bg-blue-600/10 text-blue-500 shadow-[inset_0_0_10px_rgba(37,99,235,0.05)]' 
                                        : 'text-white/40 hover:text-white/80 hover:bg-white/[0.03]'}
                                `}
                            >
                                <item.icon size={20} className={isActive ? 'text-blue-500' : 'opacity-70'} />
                                <span className="font-semibold text-sm">{item.name}</span>
                                {isActive && <div className="ml-auto w-1 h-4 bg-blue-500 rounded-full shadow-[0_0_8px_rgba(37,99,235,0.8)]" />}
                            </Link>
                        );
                    })}
                </nav>

                {/* User Profile Section */}
                <div className="relative mt-auto p-4 mx-2 mb-2 rounded-2xl bg-white/[0.02] border border-white/5 shadow-2xl overflow-hidden group">
                    <div className="absolute inset-0 bg-blue-600/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                    
                    <button
                        onClick={() => setShowProfileMenu(!showProfileMenu)}
                        className="w-full flex items-center gap-3 relative z-10 p-2"
                    >
                        <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl flex items-center justify-center text-sm font-bold shadow-lg shrink-0">
                            {userName ? userName[0].toUpperCase() : "U"}
                        </div>
                        <div className="flex-1 text-left min-w-0">
                            <div className="font-bold text-sm truncate text-white/90 group-hover:text-white transition-colors">{userName || "User"}</div>
                            <div className="text-[10px] text-white/30 truncate group-hover:text-white/50 transition-colors uppercase font-black tracking-widest">{userEmail || "Starter Plan"}</div>
                        </div>
                        <div className="flex items-center gap-2">
                            <Link 
                                href="/dashboard/profile"
                                onClick={(e) => e.stopPropagation()}
                                className="p-1.5 hover:bg-white/10 rounded-lg transition-colors text-white/20 hover:text-white/60"
                                title="Profile Settings"
                            >
                                <Settings size={16} />
                            </Link>
                            <ChevronUp size={16} className={`text-white/20 transition-transform duration-300 group-hover:text-white/40 ${showProfileMenu ? '' : 'rotate-180'}`} />
                        </div>
                    </button>

                    {/* Dropdown Menu */}
                    <AnimatePresence>
                        {showProfileMenu && (
                            <motion.div 
                                initial={{ opacity: 0, y: 10, scale: 0.95 }}
                                animate={{ opacity: 1, y: 0, scale: 1 }}
                                exit={{ opacity: 0, y: 10, scale: 0.95 }}
                                className="absolute bottom-full left-0 right-0 mb-4 bg-[#111] border border-white/10 rounded-2xl overflow-hidden shadow-2xl z-50"
                            >
                                <div className="p-4 bg-white/[0.02] border-b border-white/5">
                                    <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-yellow-500/80">
                                        <Crown size={12} className="text-yellow-500" />
                                        Starter Plan
                                    </div>
                                </div>
                                <Link
                                    href="/dashboard/profile"
                                    className="flex items-center gap-3 px-4 py-3.5 text-sm font-medium hover:bg-white/5 transition-colors group/item"
                                    onClick={() => setShowProfileMenu(false)}
                                >
                                    <User size={18} className="text-white/40 group-hover/item:text-blue-400 transition-colors" />
                                    Profile Settings
                                </Link>
                                <button
                                    onClick={handleLogout}
                                    className="w-full flex items-center gap-3 px-4 py-3.5 text-sm font-medium text-red-400/80 hover:bg-red-500/10 hover:text-red-400 transition-all group/item"
                                >
                                    <LogOut size={18} className="text-red-400/60 group-hover/item:text-red-400 transition-colors" />
                                    Logout Account
                                </button>
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>
            </aside>

            {/* Overlay for mobile sidebar */}
            {isSidebarOpen && (
                <div 
                    className="fixed inset-0 bg-black/60 backdrop-blur-sm z-30 lg:hidden"
                    onClick={() => setIsSidebarOpen(false)}
                />
            )}

            {/* Main */}
            <main className="flex-1 p-6 lg:p-12 mt-16 lg:mt-0">
                <header className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-12">
                    <div>
                        <h2 className="text-3xl lg:text-4xl font-black bg-gradient-to-r from-white to-white/40 bg-clip-text text-transparent italic">Your Bots</h2>
                        <p className="text-white/40 mt-2 font-medium">Manage and monitor your specialized AI assistants</p>
                    </div>
                    <button
                        onClick={handleCreateBot}
                        disabled={creatingBot}
                        className={`flex items-center gap-2 px-6 py-3 bg-blue-600 rounded-full font-bold hover:bg-blue-500 transition-all shadow-[0_4px_20px_rgba(37,99,235,0.3)] hover:shadow-[0_4px_25px_rgba(37,99,235,0.5)] ${creatingBot ? "opacity-70 cursor-not-allowed" : ""}`}
                    >
                        {creatingBot ? (
                            <>
                                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                Creating...
                            </>
                        ) : (
                            <>
                                <Plus size={20} /> Create New Bot
                            </>
                        )}
                    </button>
                </header>

                <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {loading ? (
                        <div className="col-span-full flex flex-col items-center justify-center py-32 space-y-4">
                            <div className="w-12 h-12 border-4 border-blue-600/20 border-t-blue-600 rounded-full animate-spin" />
                            <p className="text-white/40 font-medium animate-pulse">Synchronizing your bots...</p>
                        </div>
                    ) : bots.length === 0 ? (
                        <div className="col-span-full text-center py-32 bg-white/[0.02] rounded-[3rem] border border-dashed border-white/10 mx-4">
                            <div className="w-20 h-20 bg-white/5 rounded-3xl flex items-center justify-center mx-auto mb-6">
                                <Plus size={32} className="text-white/20" />
                            </div>
                            <h3 className="text-2xl font-bold mb-2">No bots found</h3>
                            <p className="text-white/40 mb-8 max-w-xs mx-auto text-sm">Create your first AI assistant to start automating your conversations.</p>
                            <button 
                                onClick={handleCreateBot} 
                                className="px-8 py-3 bg-blue-600 rounded-full font-bold hover:bg-blue-500 transition-all shadow-[0_0_30px_rgba(37,99,235,0.2)]"
                            >
                                Start Building
                            </button>
                        </div>
                    ) : bots.map(bot => (
                        <div 
                            key={bot.id} 
                            onClick={() => router.push(`/dashboard/builder/${bot.id}`)}
                            className="group relative p-8 rounded-[2.5rem] bg-[#0c0c0c] border border-white/5 hover:border-blue-500/30 transition-all duration-500 cursor-pointer overflow-hidden shadow-2xl"
                        >
                            {/* Card Background Glow */}
                            <div className="absolute -inset-2 bg-gradient-to-br from-blue-600/10 to-purple-600/10 opacity-0 group-hover:opacity-100 blur-2xl transition-opacity duration-500" />
                            
                            <div className="relative z-10">
                                <div className="flex items-center justify-between mb-8">
                                    <div className="w-14 h-14 bg-gradient-to-br from-white/10 to-white/[0.02] rounded-2xl flex items-center justify-center group-hover:scale-110 group-hover:bg-blue-600/10 transition-all duration-500 border border-white/5 group-hover:border-blue-500/20">
                                        <Bot size={28} className="text-white/60 group-hover:text-blue-500 transition-colors" />
                                    </div>
                                    <div className="flex flex-col items-end gap-1.5">
                                        <span className="px-3 py-1 bg-green-500/10 text-green-400 text-[10px] font-black uppercase tracking-widest rounded-full border border-green-500/20">
                                            {bot.status}
                                        </span>
                                    </div>
                                </div>
                                
                                <h3 className="text-2xl font-bold mb-3 group-hover:text-blue-400 transition-colors duration-300 tracking-tight">{bot.name}</h3>
                                
                                <div className="flex items-center gap-6 text-xs text-white/30 font-medium">
                                    <div className="flex items-center gap-2">
                                        <div className="w-1.5 h-1.5 rounded-full bg-blue-500/40 animate-pulse" />
                                        <span>{bot.conversations || 0} Interactions</span>
                                    </div>
                                    <span>Last used {bot.lastActive || "Recently"}</span>
                                </div>

                                <div className="mt-10 flex gap-3">
                                    <Link 
                                        href={`/dashboard/builder/${bot.id}`} 
                                        onClick={(e) => e.stopPropagation()}
                                        className="flex-1 py-4 bg-white/5 rounded-2xl text-center text-xs font-black uppercase tracking-widest hover:bg-blue-600 hover:text-white transition-all duration-300 border border-white/5 hover:border-blue-500/50 shadow-xl"
                                    >
                                        Edit Interface
                                    </Link>
                                    <button
                                        onClick={(e) => handleDeleteBot(bot.id, bot.name, e)}
                                        className="p-4 bg-white/[0.02] border border-white/5 rounded-2xl hover:bg-red-500/10 hover:border-red-500/30 transition-all duration-300 text-white/20 hover:text-red-500"
                                        title="Delete Bot"
                                    >
                                        <LogOut size={18} />
                                    </button>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </main>
        </div>
    );
}

