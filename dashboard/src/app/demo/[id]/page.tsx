"use client";

import { use, useEffect, useState, Suspense } from "react";
import { Bot, ChevronLeft, ExternalLink, AlertCircle } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

function DemoContent({ params }: { params: Promise<{ id: string }> }) {
    const { id: pathId } = use(params);
    const searchParams = useSearchParams();
    
    // Resolve ID from path or query params
    const id = (pathId && pathId !== "undefined" && pathId.length > 5) 
        ? pathId 
        : (searchParams.get("id") || Array.from(searchParams.keys())[0] || "");
        
    const [botName, setBotName] = useState("Loading...");
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!id || id === "undefined") {
            setError("No Bot ID provided. Please access this page from the Dashboard.");
            return;
        }

        const fetchConfig = async () => {
            try {
                const apiUrl = process.env.NEXT_PUBLIC_API_URL || "https://api.nimmiai.in";
                const res = await fetch(`${apiUrl}/api/bots/${id}/config`);
                const data = await res.json();
                if (res.ok) {
                    setBotName(data.bot_name || "Nimmi Assistant");
                } else {
                    setError(`Bot not found (ID: ${id})`);
                }
            } catch (err) {
                console.error("Failed to fetch bot config:", err);
                setError("Connection error to backend.");
            }
        };
        fetchConfig();

        // Load widget script
        const script = document.createElement("script");
        script.src = "/widget.js";
        script.setAttribute("data-bot-id", id);
        script.setAttribute("data-api-url", process.env.NEXT_PUBLIC_API_URL || "https://api.nimmiai.in");
        script.async = true;
        document.body.appendChild(script);

        return () => {
            document.body.removeChild(script);
            // Clean up injected widget elements if any
            const container = document.getElementById("nimmi-widget-container");
            if (container) container.remove();
        };
    }, [id]);

    return (
        <div className="min-h-screen bg-[#050505] text-white flex flex-col items-center justify-center p-8 relative overflow-hidden">
            {/* Background Glows */}
            <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] bg-blue-600/10 blur-[150px] rounded-full" />
            <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] bg-purple-600/5 blur-[120px] rounded-full" />

            <div className="relative z-10 max-w-2xl w-full text-center space-y-8">
                <div className="flex justify-center">
                    <div className="w-20 h-20 bg-blue-600/20 rounded-3xl flex items-center justify-center border border-blue-500/30">
                        {error ? <AlertCircle size={40} className="text-red-500" /> : <Bot size={40} className="text-blue-500" />}
                    </div>
                </div>

                <div className="space-y-4">
                    {error ? (
                        <>
                            <h1 className="text-4xl font-bold tracking-tight text-red-400">Oops!</h1>
                            <p className="text-white/60 text-lg">{error}</p>
                        </>
                    ) : (
                        <>
                            <h1 className="text-4xl font-bold tracking-tight">
                                Demo: <span className="text-blue-500">{botName}</span>
                            </h1>
                            <p className="text-white/40 text-lg">
                                You are currently viewing a live working demo of your created bot.
                                The Nimmi AI widget should appear in the bottom corner of your screen.
                            </p>
                        </>
                    )}
                </div>

                {!error && (
                    <div className="p-6 bg-white/5 border border-white/10 rounded-2xl flex items-center gap-4 text-left">
                        <div className="w-10 h-10 bg-white/10 rounded-xl flex items-center justify-center font-bold">1</div>
                        <div>
                            <p className="font-bold">Interact with the Bubble</p>
                            <p className="text-sm text-white/40">Click the chat icon in the bottom right (or left) to open the bot.</p>
                        </div>
                    </div>
                )}

                <div className="flex items-center justify-center gap-4 pt-8">
                    <Link
                        href={id && id !== "undefined" ? `/dashboard/builder/${id}` : "/dashboard"}
                        className="flex items-center gap-2 px-6 py-3 bg-white/5 hover:bg-white/10 rounded-xl font-bold transition-all border border-white/10"
                    >
                        <ChevronLeft size={20} /> Back to {id && id !== "undefined" ? "Builder" : "Dashboard"}
                    </Link>
                    <button
                        onClick={() => {
                            localStorage.removeItem(`nimmi_history_${id}`);
                            window.location.reload();
                        }}
                        className="flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-500 rounded-xl font-bold transition-all"
                    >
                        Restart Demo
                    </button>
                </div>
            </div>

            <div className="absolute bottom-8 left-1/2 -translate-x-1/2 text-white/20 text-xs uppercase tracking-widest flex items-center gap-2">
                Powered by Nimmi AI <ExternalLink size={12} />
            </div>
        </div>
    );
}

export default function DemoPage({ params }: { params: Promise<{ id: string }> }) {
    return (
        <Suspense fallback={
            <div className="min-h-screen bg-[#050505] text-white flex items-center justify-center">
                <div className="w-12 h-12 border-4 border-blue-600/10 border-t-blue-600 rounded-full animate-spin" />
            </div>
        }>
            <DemoContent params={params} />
        </Suspense>
    );
}
