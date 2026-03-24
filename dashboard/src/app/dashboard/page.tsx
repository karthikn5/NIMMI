"use client";

import { Bot, Plus, Settings, BarChart2, LayoutDashboard, Database, User, MessageSquare, LogOut, ChevronUp, Crown } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export default function Dashboard() {
    const [bots, setBots] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [userName, setUserName] = useState("");
    const [userEmail, setUserEmail] = useState("");
    const [showProfileMenu, setShowProfileMenu] = useState(false);
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
            }
        } catch (err) {
            console.error("Failed to create bot:", err);
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
            {/* Sidebar */}
            <aside className="w-64 border-r border-white/5 p-6 flex flex-col">
                <div className="flex items-center gap-2 font-bold text-xl mb-8">
                    <Bot className="text-blue-500" />
                    Nimmi AI
                </div>

                <nav className="flex-1 flex flex-col gap-2">
                    <Link href="/dashboard" className="flex items-center gap-3 px-4 py-3 bg-white/10 rounded-xl text-white">
                        <LayoutDashboard size={20} /> Dashboard
                    </Link>
                    <Link href="#" className="flex items-center gap-3 px-4 py-3 text-white/50 hover:bg-white/5 rounded-xl transition-colors">
                        <BarChart2 size={20} /> Analytics
                    </Link>
                    <Link href="#" className="flex items-center gap-3 px-4 py-3 text-white/50 hover:bg-white/5 rounded-xl transition-colors">
                        <Database size={20} /> Knowledge Base
                    </Link>
                    <Link href="#" className="flex items-center gap-3 px-4 py-3 text-white/50 hover:bg-white/5 rounded-xl transition-colors">
                        <Settings size={20} /> Settings
                    </Link>
                </nav>

                {/* User Profile Section */}
                <div className="relative mt-auto pt-6 border-t border-white/5">
                    <button
                        onClick={() => setShowProfileMenu(!showProfileMenu)}
                        className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-white/5 transition-colors group"
                    >
                        {/* Avatar */}
                        <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl flex items-center justify-center text-sm font-bold shrink-0">
                            {userName ? userName[0].toUpperCase() : "U"}
                        </div>

                        {/* Name & Email */}
                        <div className="flex-1 text-left min-w-0">
                            <div className="font-semibold text-sm truncate">{userName || "User"}</div>
                            <div className="text-xs text-white/40 truncate">{userEmail || "Loading..."}</div>
                        </div>

                        {/* Chevron */}
                        <ChevronUp size={16} className={`text-white/40 transition-transform ${showProfileMenu ? '' : 'rotate-180'}`} />
                    </button>

                    {/* Dropdown Menu */}
                    {showProfileMenu && (
                        <div className="absolute bottom-full left-0 right-0 mb-2 bg-zinc-900 border border-white/10 rounded-xl overflow-hidden shadow-xl">
                            <div className="p-3 border-b border-white/5">
                                <div className="flex items-center gap-2 text-xs text-white/50">
                                    <Crown size={12} className="text-yellow-500" />
                                    Free Plan
                                </div>
                            </div>
                            <Link
                                href="/dashboard/profile"
                                className="flex items-center gap-3 px-4 py-3 text-sm hover:bg-white/5 transition-colors"
                                onClick={() => setShowProfileMenu(false)}
                            >
                                <User size={16} className="text-white/60" />
                                View Profile
                            </Link>
                            <button
                                onClick={handleLogout}
                                className="w-full flex items-center gap-3 px-4 py-3 text-sm text-red-400 hover:bg-red-500/10 transition-colors"
                            >
                                <LogOut size={16} />
                                Log Out
                            </button>
                        </div>
                    )}
                </div>
            </aside>

            {/* Main */}
            <main className="flex-1 p-10">
                <header className="flex items-center justify-between mb-12">
                    <div>
                        <h2 className="text-3xl font-bold">Your Bots</h2>
                        <p className="text-white/50 mt-1">Manage and monitor your AI assistants</p>
                    </div>
                    <button
                        onClick={handleCreateBot}
                        className="flex items-center gap-2 px-6 py-3 bg-blue-600 rounded-full font-bold hover:bg-blue-500 transition-colors"
                    >
                        <Plus size={20} /> Create New Bot
                    </button>
                </header>

                <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {loading ? (
                        <div className="col-span-full text-center py-20 text-white/20">Loading bots...</div>
                    ) : bots.length === 0 ? (
                        <div className="col-span-full text-center py-20 bg-white/5 rounded-3xl border border-dashed border-white/10">
                            <p className="text-white/40 mb-4">You haven't created any bots yet.</p>
                            <button onClick={handleCreateBot} className="text-blue-500 font-bold hover:underline">Create your first bot</button>
                        </div>
                    ) : bots.map(bot => (
                        <div key={bot.id} className="group p-6 rounded-3xl bg-zinc-900 border border-white/5 hover:border-white/10 transition-all cursor-pointer">
                            <div className="flex items-center justify-between mb-6">
                                <div className="w-12 h-12 bg-white/5 rounded-2xl flex items-center justify-center group-hover:bg-blue-600/20 transition-colors">
                                    <Bot className="text-white group-hover:text-blue-500 transition-colors" />
                                </div>
                                <span className="px-3 py-1 bg-green-500/10 text-green-500 text-xs font-bold rounded-full border border-green-500/20">
                                    {bot.status}
                                </span>
                            </div>
                            <h3 className="text-xl font-bold mb-2">{bot.name}</h3>
                            <div className="flex items-center gap-6 text-sm text-white/40">
                                <span className="flex items-center gap-1.5"><MessageSquare size={14} /> {bot.conversations} chats</span>
                                <span>Active {bot.lastActive}</span>
                            </div>
                            <div className="mt-8 flex gap-2">
                                <Link href={`/dashboard/builder/${bot.id}`} className="flex-1 py-3 bg-white/5 rounded-xl text-center text-sm font-bold hover:bg-white/10 transition-colors">
                                    Edit Bot
                                </Link>
                                <button
                                    onClick={(e) => handleDeleteBot(bot.id, bot.name, e)}
                                    className="p-3 bg-white/5 rounded-xl hover:bg-red-500/20 hover:text-red-500 transition-colors group-delete"
                                    title="Delete Bot"
                                >
                                    <LogOut size={18} className="text-white/60 group-delete-hover:text-red-500 transition-colors" />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            </main>
        </div>
    );
}

