"use client";

import { useEffect, useState } from "react";
import { Check, CreditCard, Clock, ShieldCheck, Zap, ArrowRight, Bot, Star, Crown, MessageSquare, Plus, ArrowLeft, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import NextImage from "next/image";

const PLANS = [
  {
    name: "1 Month Plan",
    duration: "1 Month",
    originalPrice: "₹299",
    price: "₹1",
    monthlyEquivalent: "₹1/month",
    description: "Perfect for trying NIMMI AI",
    buttonText: "Choose Plan",
    highlighted: false,
    icon: <NextImage src="/icons/star.png" alt="Star" width={40} height={40} className="object-contain" />,
    features: [
      "Full Access for 1 Bot",
      "Unlimited Conversations",
      "Train on PDFs & Text",
      "Export Code Unlocked",
      "Standard Response Time"
    ]
  },
  {
    name: "6 Month Plan",
    duration: "6 Months",
    originalPrice: "₹1499",
    price: "₹499",
    monthlyEquivalent: "₹83/month",
    description: "Best for regular users",
    buttonText: "Choose Plan",
    badge: "Most Popular",
    highlighted: true,
    icon: <NextImage src="/icons/fire.png" alt="Fire" width={40} height={40} className="object-contain" />,
    features: [
      "Full Access for 1 Bot",
      "Unlimited Conversations",
      "Train on Website URLs",
      "Export Code Unlocked",
      "Fast Response Time",
      "Priority Support"
    ]
  },
  {
    name: "12 Month Plan",
    duration: "12 Months",
    originalPrice: "₹2599",
    price: "₹999",
    monthlyEquivalent: "₹83/month",
    description: "Save more with long-term access",
    buttonText: "Choose Plan",
    badge: "Best Value",
    highlighted: false,
    icon: <NextImage src="/icons/diamond.png" alt="Diamond" width={40} height={40} className="object-contain" />,
    features: [
      "Full Access for 1 Bot",
      "Unlimited Conversations",
      "Auto-Sync Data Source",
      "Export Code Unlocked",
      "Lightning Fast API",
      "API Access"
    ]
  }
];

export default function BillingPage() {
    const [usage, setUsage] = useState<any>(null);
    const [subscription, setSubscription] = useState<any>(null);
    const [history, setHistory] = useState<any[]>([]);
    const [bots, setBots] = useState<any[]>([]);
    const [selectedBotId, setSelectedBotId] = useState<string>("");
    const [selectedPlan, setSelectedPlan] = useState<any>(null);
    const [showBotSelector, setShowBotSelector] = useState(false);
    const [loading, setLoading] = useState(true);
    const [processing, setProcessing] = useState<string | null>(null);
    const router = useRouter();

    useEffect(() => {
        let userId = localStorage.getItem("nimmi_user_id");
        if (!userId) {
            router.push("/auth/signup");
            return;
        }
        userId = userId.trim();

        // ⚡ Speed Optimization: Load from cache first
        const cachedUsage = localStorage.getItem(`usage_${userId}`);
        const cachedSub = localStorage.getItem(`sub_${userId}`);
        const cachedHistory = localStorage.getItem(`history_${userId}`);
        if (cachedUsage) setUsage(JSON.parse(cachedUsage));
        if (cachedSub) setSubscription(JSON.parse(cachedSub));
        if (cachedHistory) setHistory(JSON.parse(cachedHistory));

        const fetchData = async () => {
            try {
                const apiUrl = typeof window !== "undefined" && (window.location.hostname.includes("nimmiai.in") || window.location.hostname.includes("railway.app"))
                    ? "https://api.nimmiai.in"
                    : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");
                
                const [usageRes, historyRes, botsRes] = await Promise.all([
                    fetch(`${apiUrl}/api/usage?user_id=${userId}`),
                    fetch(`${apiUrl}/api/payments/history?user_id=${userId}`),
                    fetch(`${apiUrl}/api/bots?user_id=${userId}`)
                ]);
                
                if (usageRes.ok) {
                    const usageData = await usageRes.json();
                    setUsage(usageData);
                    localStorage.setItem(`usage_${userId}`, JSON.stringify(usageData));
                }

                // Fetch subscriptions to find the latest active one
                try {
                    const subRes = await fetch(`${apiUrl}/api/payments/subscriptions?user_id=${userId}`);
                    if (subRes.ok) {
                        const subsData = await subRes.json();
                        // Find the first active subscription
                        const activeSub = subsData.find((s: any) => s.status === "active");
                        if (activeSub) {
                            setSubscription(activeSub);
                            localStorage.setItem(`sub_${userId}`, JSON.stringify(activeSub));
                        } else {
                            setSubscription(null);
                            localStorage.removeItem(`sub_${userId}`);
                        }
                    }
                } catch (subErr) {
                    console.error("Sub fetch failed", subErr);
                }
                
                if (historyRes.ok) {
                    const historyData = await historyRes.json();
                    setHistory(historyData);
                    localStorage.setItem(`history_${userId}`, JSON.stringify(historyData));
                }

                if (botsRes.ok) {
                    const botsData = await botsRes.json();
                    setBots(botsData);
                    if (botsData.length > 0) setSelectedBotId(botsData[0].id);
                }
            } catch (err) {
                console.error("Failed to fetch billing data", err);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
        
        if (!document.getElementById("razorpay-sdk")) {
            const script = document.createElement("script");
            script.id = "razorpay-sdk";
            script.src = "https://checkout.razorpay.com/v1/checkout.js";
            script.async = true;
            document.body.appendChild(script);
        }
    }, [router]);

    const handlePlanSelect = (plan: any) => {
        if (bots.length === 0) {
            alert("Please create a chatbot first before purchasing a plan.");
            router.push("/dashboard");
            return;
        }
        setSelectedPlan(plan);
        setShowBotSelector(true);
    };

    const handlePurchase = async () => {
        if (!selectedPlan || !selectedBotId) return;
        
        const plan = selectedPlan;
        const userId = localStorage.getItem("nimmi_user_id");
        const userName = localStorage.getItem("nimmi_user_name");
        const userEmail = localStorage.getItem("nimmi_user_email");
        
        if (!userId) return;
        
        setProcessing(plan.name);
        try {
            const apiUrl = typeof window !== "undefined" && (window.location.hostname.includes("nimmiai.in") || window.location.hostname.includes("railway.app"))
                ? "https://api.nimmiai.in"
                : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");

            const res = await fetch(`${apiUrl}/api/payments/create-subscription-order`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    plan_name: plan.name,
                    user_id: userId,
                    bot_id: selectedBotId
                })
            });
            
            const orderData = await res.json();
            if (!res.ok) {
                let errorMsg = "Failed to create order";
                if (orderData.detail) {
                    if (Array.isArray(orderData.detail)) {
                        const err = orderData.detail[0];
                        const field = err.loc[err.loc.length - 1];
                        errorMsg = `${field}: ${err.msg}`;
                    } else {
                        errorMsg = orderData.detail;
                    }
                }
                throw new Error(errorMsg);
            }

            const options = {
                key: orderData.key_id,
                amount: orderData.amount,
                currency: orderData.currency,
                name: "Nimmi AI",
                description: `Purchase ${plan.name}`,
                order_id: orderData.order_id,
                handler: async function (response: any) {
                    try {
                        const verifyRes = await fetch(`${apiUrl}/api/payments/verify`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                razorpay_order_id: response.razorpay_order_id,
                                razorpay_payment_id: response.razorpay_payment_id,
                                razorpay_signature: response.razorpay_signature,
                                user_id: userId,
                                bot_id: selectedBotId,
                                plan_name: plan.name
                            })
                        });
                        
                        if (verifyRes.ok) {
                            alert(`Success! ${plan.name} activated for your chatbot.`);
                            window.location.reload();
                        } else {
                            alert("Payment verification failed.");
                        }
                    } catch (verifyErr: any) {
                        alert("Verification error: " + verifyErr.message);
                    }
                },
                prefill: {
                    name: userName || "",
                    email: userEmail || "",
                },
                theme: {
                    color: "#9d55ac",
                },
                modal: {
                    ondismiss: function() {
                        setProcessing(null);
                    }
                }
            };

            const rzp = new (window as any).Razorpay(options);
            rzp.open();
        } catch (err: any) {
            console.error("Purchase error:", err);
            alert(err.message || "An unexpected error occurred");
        } finally {
            setProcessing(null);
        }
    };

    const formatDate = (dateStr: string) => {
        if (!dateStr) return "N/A";
        try {
            const date = new Date(dateStr);
            if (isNaN(date.getTime())) return "N/A";
            return date.toLocaleDateString('en-IN', {
                day: 'numeric',
                month: 'short',
                year: 'numeric'
            });
        } catch (e) {
            return "N/A";
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
            <div className="max-w-6xl mx-auto">
                <div className="mb-8">
                    <button 
                        onClick={() => router.back()}
                        className="group flex items-center gap-2 px-4 py-2 bg-white border border-zinc-200 rounded-2xl text-zinc-600 font-bold text-sm hover:bg-zinc-50 transition-all hover:shadow-md active:scale-95"
                    >
                        <ArrowLeft size={18} className="group-hover:-translate-x-1 transition-transform" />
                        Back to Dashboard
                    </button>
                </div>

                <header className="mb-12 text-center lg:text-left">
                    <motion.div
                        initial={{ opacity: 0, y: -20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="inline-flex items-center gap-2 px-4 py-1.5 bg-purple-50 border border-purple-100 rounded-full mb-4"
                    >
                        <span className="text-xs font-bold text-[#9d55ac] uppercase tracking-wider">Billing Dashboard</span>
                    </motion.div>
                    <h1 className="text-4xl md:text-5xl font-bold text-zinc-900 mb-3 tracking-tight">
                        Membership & <span className="text-[#9d55ac]">Billing</span>
                    </h1>
                    <p className="text-zinc-500 font-medium max-w-2xl">Manage your subscription, chatbot credits, and payment history in one place.</p>
                </header>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-16">
                    <motion.div 
                        whileHover={{ y: -5 }}
                        className="bg-white p-8 rounded-[2.5rem] shadow-[0_20px_50px_rgba(0,0,0,0.04)] border border-white relative overflow-hidden group"
                    >
                        <div className="absolute top-0 right-0 p-8 opacity-[0.03] group-hover:opacity-[0.05] transition-opacity">
                            <Bot size={120} />
                        </div>
                        <div className="flex items-center gap-4 mb-8">
                            <div className="w-16 h-16 bg-purple-50 rounded-2xl flex items-center justify-center shadow-inner overflow-hidden">
                                <Sparkles size={32} className="text-[#9d55ac]" />
                            </div>
                            <div>
                                <h3 className="text-sm font-bold text-zinc-400 uppercase tracking-widest">Platform Model</h3>
                                <p className="text-zinc-900 font-bold">Bot-Based Subscription</p>
                            </div>
                        </div>
                        <div className="flex items-baseline gap-2 mb-2">
                            <span className="text-6xl font-bold text-zinc-900 tracking-tighter">{bots.length}</span>
                            <span className="text-zinc-400 font-bold text-lg">Total Bots</span>
                        </div>
                        <p className="text-zinc-500 text-sm font-medium">Each bot requires its own active plan for API & export.</p>
                    </motion.div>

                    <motion.div 
                        whileHover={{ y: -5 }}
                        className="bg-zinc-900 p-8 rounded-[2.5rem] text-white shadow-2xl shadow-purple-900/10 relative overflow-hidden group"
                    >
                        <div className="absolute top-0 right-0 p-8 opacity-[0.05] group-hover:opacity-[0.1] transition-opacity">
                            <Crown size={120} />
                        </div>
                        <div className="flex items-center gap-4 mb-8">
                            <div className="w-16 h-16 bg-white/10 rounded-2xl flex items-center justify-center shadow-inner overflow-hidden border border-white/20">
                                <NextImage src="/icons/crown.png" alt="Crown" width={48} height={48} className="object-contain" />
                            </div>
                            <div>
                                <h3 className="text-sm font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
                                    Current Status
                                    {subscription && (
                                        <motion.span 
                                            animate={{ scale: [1, 1.2, 1] }} 
                                            transition={{ repeat: Infinity, duration: 2 }}
                                            className="w-2 h-2 bg-green-500 rounded-full shadow-[0_0_10px_#22c55e]"
                                        />
                                    )}
                                </h3>
                                <p className="text-white font-bold text-lg">
                                    {(subscription || (usage?.subscription_tier && usage?.subscription_tier !== 'Free')) 
                                        ? `Welcome back, ${localStorage.getItem("nimmi_user_name")?.split(' ')[0] || 'Premium Member'}! 🚀`
                                        : "Free Member"}
                                </p>
                            </div>
                        </div>
                        <div className="mb-4">
                            <div className="flex items-center gap-3">
                                <span className="text-4xl font-bold italic tracking-tight">
                                    {subscription?.plan_name || 
                                     (usage?.subscription_tier && usage?.subscription_tier !== 'Free' 
                                        ? usage.subscription_tier 
                                        : "Free Tier")}
                                </span>
                                {(subscription || (usage?.subscription_tier && usage?.subscription_tier !== 'Free')) && (
                                    <span className="px-3 py-1 bg-gradient-to-r from-yellow-500 to-amber-600 rounded-full text-[10px] font-black uppercase tracking-widest text-white shadow-lg">
                                        Active
                                    </span>
                                )}
                            </div>
                        </div>
                        <div className="flex items-center gap-2 text-zinc-400 text-sm font-medium">
                            {(subscription || (usage?.subscription_tier && usage?.subscription_tier !== 'Free')) ? (
                                <>
                                    <ShieldCheck size={16} className="text-[#9d55ac]" />
                                    <span>
                                        {subscription 
                                            ? `Premium Access until ${formatDate(subscription.end_date)}` 
                                            : "Premium Subscription Active"}
                                    </span>
                                </>
                            ) : (
                                <>
                                    <Sparkles size={16} className="text-yellow-500 animate-pulse" />
                                    <span>Upgrade to unlock superpowers! ✨</span>
                                </>
                            )}
                        </div>
                    </motion.div>
                </div>

                <div className="mb-16">
                    <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-10 text-center md:text-left">
                        <div>
                            <h2 className="text-3xl font-bold text-zinc-900 tracking-tight mb-2">Choose your Plan</h2>
                            <p className="text-zinc-500 font-medium">Select the best value for your AI journey.</p>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                        {PLANS.map((plan, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: i * 0.1 }}
                                className={`relative flex flex-col p-8 rounded-[2.5rem] transition-all duration-300 bg-white group
                                    ${plan.highlighted ? "ring-2 ring-[#9d55ac] shadow-2xl shadow-purple-900/5 scale-[1.02] z-10" : "border border-zinc-100 shadow-sm hover:shadow-xl hover:shadow-zinc-200/40"}
                                `}
                            >
                                {plan.badge && (
                                    <div className={`absolute -top-4 left-1/2 -translate-x-1/2 px-5 py-1.5 rounded-full text-xs font-black uppercase tracking-widest shadow-lg
                                        ${plan.highlighted ? "bg-[#9d55ac] text-white" : "bg-zinc-800 text-white"}
                                    `}>
                                        {plan.badge}
                                    </div>
                                )}
                                
                                <div className="mb-8">
                                    <div className="flex items-center gap-3 mb-4">
                                        <div className="p-2.5 bg-zinc-50 rounded-xl group-hover:scale-110 transition-transform">
                                            {plan.icon}
                                        </div>
                                        <h3 className="text-xl font-bold text-zinc-900">{plan.name}</h3>
                                    </div>
                                    <div className="flex items-baseline gap-2 mb-2">
                                        <span className="text-sm text-zinc-400 line-through font-bold">{plan.originalPrice}</span>
                                        <span className="text-4xl font-bold text-zinc-900">{plan.price}</span>
                                        <span className="text-zinc-400 text-sm font-bold">/ {plan.duration}</span>
                                    </div>
                                    <p className="text-zinc-500 text-xs font-semibold leading-relaxed">{plan.description}</p>
                                </div>

                                <ul className="space-y-4 mb-10 flex-grow">
                                    {plan.features.map((feature, idx) => (
                                        <li key={idx} className="flex items-start gap-3">
                                            <div className={`p-0.5 rounded-full mt-1 ${plan.highlighted ? "bg-[#9d55ac]/10 text-[#9d55ac]" : "bg-zinc-100 text-zinc-400"}`}>
                                                <Check size={12} />
                                            </div>
                                            <span className="text-zinc-600 text-xs font-medium leading-tight">{feature}</span>
                                        </li>
                                    ))}
                                </ul>

                                <button
                                    onClick={() => handlePlanSelect(plan)}
                                    disabled={processing !== null}
                                    className={`w-full py-4 rounded-2xl font-bold text-xs uppercase tracking-widest transition-all
                                        ${plan.highlighted 
                                            ? "bg-gradient-to-br from-[#9d55ac] to-[#7c3aed] text-white shadow-xl shadow-purple-900/20 hover:scale-[1.02] active:scale-[0.98]" 
                                            : "bg-zinc-50 text-zinc-900 hover:bg-zinc-100 border border-zinc-200"}
                                        ${processing === plan.name ? "opacity-50 cursor-not-allowed" : ""}
                                    `}
                                >
                                    {processing === plan.name ? "Processing..." : plan.buttonText}
                                </button>
                            </motion.div>
                        ))}
                    </div>
                </div>

                <motion.div 
                    initial={{ opacity: 0 }}
                    whileInView={{ opacity: 1 }}
                    className="bg-white border border-dashed border-zinc-200 rounded-[2.5rem] p-8 md:p-12 text-center mb-16"
                >
                    <div className="inline-flex items-center gap-3 px-4 py-1.5 bg-zinc-50 rounded-full mb-6">
                        <MessageSquare size={16} className="text-[#9d55ac]" />
                        <span className="text-xs font-bold text-zinc-500 uppercase tracking-widest">Enterprise Solution</span>
                    </div>
                    <h2 className="text-3xl font-bold text-zinc-900 mb-4">Need more Chatbots?</h2>
                    <p className="text-zinc-500 max-w-xl mx-auto mb-8 font-medium">Custom chatbot slots, dedicated infrastructure, and 24/7 support for large scale business requirements.</p>
                    <button 
                        onClick={() => window.location.href = "mailto:support@nimmiai.in"}
                        className="inline-flex items-center gap-2 px-8 py-4 bg-zinc-900 text-white rounded-2xl font-bold text-sm hover:bg-zinc-800 transition-colors"
                    >
                        Talk to Sales <ArrowRight size={18} />
                    </button>
                </motion.div>

                <div>
                    <h2 className="text-2xl font-bold text-zinc-900 mb-8 tracking-tight flex items-center gap-3">
                        <div className="w-8 h-8 bg-zinc-100 rounded-lg flex items-center justify-center">
                            <CreditCard size={16} className="text-zinc-500" />
                        </div>
                        Billing History
                    </h2>
                    <div className="bg-white border border-zinc-100 rounded-[2.5rem] overflow-hidden shadow-sm">
                        <div className="overflow-x-auto">
                            <table className="w-full text-left text-zinc-600">
                                <thead className="bg-zinc-50/50 border-b border-zinc-100">
                                    <tr>
                                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest">Plan Name</th>
                                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest">Chatbot</th>
                                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest">Date</th>
                                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest">Amount</th>
                                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest">Status</th>
                                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest">TX ID</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-zinc-50">
                                    {history.length > 0 ? history.map((tx, idx) => (
                                        <tr key={idx} className="hover:bg-zinc-50/50 transition-colors">
                                            <td className="px-8 py-6">
                                                <div className="flex items-center gap-3">
                                                    <div className="w-8 h-8 bg-purple-50 rounded-lg flex items-center justify-center">
                                                        <Zap size={14} className="text-[#9d55ac]" />
                                                    </div>
                                                    <span className="font-bold text-zinc-900 text-sm">{tx.plan_name}</span>
                                                </div>
                                            </td>
                                            <td className="px-8 py-6">
                                                <div className="flex items-center gap-2">
                                                    <div className="w-6 h-6 bg-zinc-50 rounded-md flex items-center justify-center text-zinc-400">
                                                        <Bot size={12} />
                                                    </div>
                                                    <span className="text-zinc-500 font-bold text-xs">
                                                        {bots.find(b => b.id === tx.bot_id)?.name || "Chatbot Slot"}
                                                    </span>
                                                </div>
                                            </td>
                                            <td className="px-8 py-6 text-xs font-medium text-zinc-400">{tx.date}</td>
                                            <td className="px-8 py-6 font-black text-zinc-900 text-sm">₹{tx.amount}</td>
                                            <td className="px-8 py-6">
                                                <span className="px-3 py-1 bg-green-50 text-green-600 rounded-full text-[10px] font-black uppercase tracking-widest">
                                                    {tx.status}
                                                </span>
                                            </td>
                                            <td className="px-8 py-6 text-[10px] font-mono text-zinc-300">
                                                {tx.transaction_id}
                                            </td>
                                        </tr>
                                    )) : (
                                        <tr>
                                            <td colSpan={6} className="px-8 py-12 text-center text-zinc-400 font-bold text-sm">
                                                No payment history found yet.
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>

            {/* Bot Selection Modal */}
            <AnimatePresence>
                {showBotSelector && selectedPlan && (
                    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
                        <motion.div 
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            onClick={() => setShowBotSelector(false)}
                            className="absolute inset-0 bg-zinc-900/40 backdrop-blur-sm"
                        />
                        <motion.div 
                            initial={{ opacity: 0, scale: 0.9, y: 20 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.9, y: 20 }}
                            className="relative w-full max-w-md bg-white rounded-[2.5rem] shadow-2xl p-10 overflow-hidden"
                        >
                            <div className="absolute top-0 right-0 p-10 opacity-[0.02] pointer-events-none">
                                <Crown size={150} />
                            </div>

                            <h3 className="text-2xl font-bold text-zinc-900 mb-2">Assign to Chatbot</h3>
                            <p className="text-zinc-500 text-sm font-medium mb-8">
                                You are purchasing <span className="text-[#9d55ac] font-bold">{selectedPlan.name}</span>. 
                                Select which chatbot you want to upgrade.
                            </p>

                            <div className="space-y-4 mb-8">
                                <label className="text-[10px] font-black text-zinc-400 uppercase tracking-widest">Select your Assistant</label>
                                <div className="relative">
                                    <select 
                                        value={selectedBotId}
                                        onChange={(e) => setSelectedBotId(e.target.value)}
                                        className="w-full bg-zinc-50 border border-zinc-100 p-4 rounded-2xl appearance-none font-bold text-zinc-900 text-sm focus:ring-2 focus:ring-[#9d55ac] outline-none"
                                    >
                                        {bots.map(bot => (
                                            <option key={bot.id} value={bot.id}>
                                                {bot.name} ({bot.status})
                                            </option>
                                        ))}
                                    </select>
                                    <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-zinc-400">
                                        <ArrowRight size={16} className="rotate-90" />
                                    </div>
                                </div>
                            </div>

                            <div className="flex gap-4">
                                <button 
                                    onClick={() => setShowBotSelector(false)}
                                    className="flex-grow py-4 bg-zinc-50 text-zinc-500 rounded-2xl font-bold text-xs uppercase tracking-widest hover:bg-zinc-100 transition-colors"
                                >
                                    Cancel
                                </button>
                                <button 
                                    onClick={() => {
                                        setShowBotSelector(false);
                                        handlePurchase();
                                    }}
                                    className="flex-[2] py-4 bg-[#9d55ac] text-white rounded-2xl font-bold text-xs uppercase tracking-widest shadow-xl shadow-purple-900/20 hover:scale-[1.02] transition-all"
                                >
                                    Upgrade Now
                                </button>
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>
        </div>
    );
}
