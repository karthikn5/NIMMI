"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle, ArrowRight, Sparkles } from "lucide-react";
import { motion } from "framer-motion";

function PaymentSuccessContent() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const botId = searchParams.get("bot_id");
    const [countdown, setCountdown] = useState(5);

    useEffect(() => {
        if (!botId) return;

        if (countdown <= 0) {
            router.push(`/dashboard/builder/${botId}?payment=success`);
            return;
        }

        const timer = setInterval(() => {
            setCountdown((prev) => prev - 1);
        }, 1000);

        return () => clearInterval(timer);
    }, [botId, router, countdown]);

    if (!botId) {
        return (
            <div className="min-h-screen bg-[#fcfcfd] flex items-center justify-center p-4">
                <div className="text-slate-900 text-center">
                    <h1 className="text-2xl font-bold mb-2">Invalid Session</h1>
                    <button
                        onClick={() => router.push('/dashboard')}
                        className="text-blue-600 hover:text-blue-700 transition-colors"
                    >
                        Go back to Dashboard
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[#fcfcfd] flex items-center justify-center p-4 relative overflow-hidden">
            {/* Background Decorations */}
            <div className="absolute top-1/4 left-1/4 w-64 h-64 bg-blue-400/5 rounded-full blur-[120px]" />
            <div className="absolute bottom-1/4 right-1/4 w-64 h-64 bg-purple-400/5 rounded-full blur-[120px]" />

            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="max-w-md w-full bg-white/40 backdrop-blur-2xl border border-white/40 p-8 rounded-[32px] shadow-[0_20px_50px_rgba(0,0,0,0.05)] relative z-10"
            >
                <div className="flex flex-col items-center text-center space-y-6">
                    <motion.div
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        transition={{ type: "spring", damping: 12, stiffness: 200, delay: 0.2 }}
                        className="w-20 h-20 bg-green-50 rounded-full flex items-center justify-center border border-green-100 shadow-inner"
                    >
                        <CheckCircle size={40} className="text-green-500" />
                    </motion.div>

                    <div className="space-y-2">
                        <motion.h1
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: 0.4 }}
                            className="text-3xl font-bold bg-gradient-to-b from-slate-900 to-slate-600 bg-clip-text text-transparent flex items-center justify-center gap-2"
                        >
                            Payment Successful <Sparkles size={20} className="text-yellow-500" />
                        </motion.h1>
                        <motion.p
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: 0.5 }}
                            className="text-slate-500 text-sm leading-relaxed font-medium"
                        >
                            Your export license has been activated. You can now deploy your chatbot to any platform.
                        </motion.p>
                    </div>

                    <div className="w-full h-px bg-slate-100" />

                    <div className="flex items-center justify-between w-full text-xs">
                        <span className="text-slate-400 font-bold uppercase tracking-widest">License Type</span>
                        <span className="text-slate-900 font-bold">Lifetime Export</span>
                    </div>
                    <div className="flex items-center justify-between w-full text-xs">
                        <span className="text-slate-400 font-bold uppercase tracking-widest">Status</span>
                        <span className="text-green-600 font-black uppercase tracking-widest">Active</span>
                    </div>

                    <motion.button
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        onClick={() => router.push(`/dashboard/builder/${botId}`)}
                        className="w-full py-4 bg-blue-600 text-white rounded-2xl font-bold flex items-center justify-center gap-2 group transition-all shadow-xl shadow-blue-500/20 hover:bg-blue-700"
                    >
                        Return to Builder
                        <ArrowRight size={18} className="transition-transform group-hover:translate-x-1" />
                    </motion.button>

                    <p className="text-[10px] text-slate-400 font-bold uppercase tracking-tighter">
                        Redirecting in {countdown}s...
                    </p>
                </div>
            </motion.div>
        </div>
    );
}

export default function PaymentSuccessPage() {
    return (
        <Suspense fallback={<div className="min-h-screen bg-[#fcfcfd] flex items-center justify-center text-slate-900">Loading...</div>}>
            <PaymentSuccessContent />
        </Suspense>
    );
}
