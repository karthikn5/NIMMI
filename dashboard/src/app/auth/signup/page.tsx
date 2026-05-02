"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { User, Mail, Lock, Eye, EyeOff, ArrowRight, ArrowLeft } from "lucide-react";
import Image from "next/image";
import { useEffect } from "react";
import { createClient } from "@/utils/supabase/client";
import { motion } from "framer-motion";

export default function Signup() {
    const [formData, setFormData] = useState({ name: "", email: "", password: "" });
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const router = useRouter();
    const supabase = createClient();

    useEffect(() => {
        const checkOAuth = async () => {
            const { data: { session } } = await supabase.auth.getSession();
            if (session?.user) {
                const user = session.user;
                // Sync with our backend
                try {
                    const apiUrl = typeof window !== "undefined" && window.location.hostname.includes("nimmiai.in")
                        ? "https://api.nimmiai.in"
                        : (process.env.NEXT_PUBLIC_API_URL || "https://api.nimmiai.in");
                    const res = await fetch(`${apiUrl}/api/auth/social`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ 
                            email: user.email, 
                            name: user.user_metadata.full_name || user.user_metadata.name || "",
                            provider: "google"
                        })
                    });
                    const data = await res.json();
                    if (res.ok) {
                        localStorage.setItem("nimmi_user_id", data.user_id);
                        localStorage.setItem("nimmi_user_name", data.name || "");
                        localStorage.setItem("nimmi_user_email", user.email!);
                        router.push("/dashboard");
                    }
                } catch (err) {
                    console.error("OAuth Sync Error:", err);
                }
            }
        };
        checkOAuth();
    }, [supabase, router]);

    const handleGoogleSignup = async () => {
        const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || window.location.origin;
        await supabase.auth.signInWithOAuth({
            provider: 'google',
            options: {
                redirectTo: `${siteUrl}/auth/signup`
            }
        });
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError("");
        try {
            const apiUrl = typeof window !== "undefined" && window.location.hostname.includes("nimmiai.in")
                ? "https://api.nimmiai.in"
                : (process.env.NEXT_PUBLIC_API_URL || "https://api.nimmiai.in");
            const res = await fetch(`${apiUrl}/api/auth/signup`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: formData.name, email: formData.email, password: formData.password })
            });
            const data = await res.json();
            if (res.ok) {
                localStorage.setItem("nimmi_user_id", data.user_id);
                localStorage.setItem("nimmi_user_name", data.name || formData.name);
                localStorage.setItem("nimmi_user_email", formData.email);
                router.push("/dashboard");
            } else {
                setError(data.detail || "Signup failed");
            }
        } catch {
            setError("Could not connect to backend");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-[#fcfcfd] flex items-center justify-center p-6 relative overflow-hidden">
            {/* Back Button */}
            <Link href="/" className="absolute top-8 left-8 flex items-center gap-2 text-zinc-500 hover:text-zinc-900 transition-colors z-20 group">
                <div className="w-8 h-8 rounded-full border border-zinc-200 flex items-center justify-center group-hover:border-zinc-300 transition-colors">
                    <ArrowLeft size={16} />
                </div>
                <span className="text-sm font-medium">Back to Home</span>
            </Link>
            {/* Background Accents */}
            <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-purple-400/5 blur-[120px] rounded-full" />
            <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-400/5 blur-[120px] rounded-full" />

            <div className="w-full max-w-5xl grid grid-cols-1 md:grid-cols-2 gap-12 items-center z-10">
                {/* Left Side: Visual/Branding */}
                <div className="hidden md:flex flex-col items-start space-y-8 p-8">
                    <div className="space-y-4">
                        <h2 className="text-4xl font-bold text-zinc-900 leading-tight">
                            Start building <span className="text-[#9d55ac]">smarter</span> bots.
                        </h2>
                        <p className="text-zinc-500 text-lg max-w-sm">
                            Create your account and launch your first AI assistant in less than 2 minutes.
                        </p>
                    </div>
                    <div className="relative w-full aspect-square max-w-sm">
                        <motion.div
                            animate={{ y: [0, -15, 0] }}
                            transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
                            className="relative w-full h-full"
                        >
                            <Image 
                                src="/login-mascot-v3.png" 
                                alt="Nimmi Mascot" 
                                fill 
                                className="object-contain drop-shadow-2xl mix-blend-multiply" 
                            />
                        </motion.div>
                    </div>
                </div>

                {/* Right Side: Form */}
                <div className="w-full max-w-md mx-auto">
                    <div className="bg-white border border-zinc-100 rounded-[2.5rem] p-10 shadow-[0_20px_50px_rgba(0,0,0,0.04)]">
                        <div className="text-center mb-8">
                            <div className="md:hidden inline-flex items-center justify-center w-16 h-16 bg-purple-50 rounded-2xl border border-purple-100 mb-6 overflow-hidden relative">
                                <Image src="/nimmi-logo-new.png" alt="Nimmi Logo" fill className="object-contain p-3" />
                            </div>
                            <h1 className="text-3xl font-bold text-zinc-900">Create Account</h1>
                            <p className="text-zinc-500 mt-2 font-medium">Join Nimmi AI and start building</p>
                        </div>

                        <form onSubmit={handleSubmit} className="space-y-6">
                            {/* Name */}
                            <div className="space-y-2">
                                <label className="text-xs font-bold text-zinc-400 uppercase tracking-widest ml-1">Full Name</label>
                                <div className="relative group">
                                    <User className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 group-focus-within:text-[#9d55ac] transition-colors" size={20} />
                                    <input
                                        type="text"
                                        required
                                        placeholder="John Doe"
                                        value={formData.name}
                                        onChange={e => setFormData({ ...formData, name: e.target.value })}
                                        className="w-full bg-zinc-50/50 border border-zinc-100 rounded-2xl py-4 pl-12 pr-4 outline-none focus:border-[#9d55ac] focus:bg-white transition-all text-zinc-900 font-medium placeholder:text-zinc-300"
                                    />
                                </div>
                            </div>

                            {/* Email */}
                            <div className="space-y-2">
                                <label className="text-xs font-bold text-zinc-400 uppercase tracking-widest ml-1">Email Address</label>
                                <div className="relative group">
                                    <Mail className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 group-focus-within:text-[#9d55ac] transition-colors" size={20} />
                                    <input
                                        type="email"
                                        required
                                        placeholder="name@example.com"
                                        value={formData.email}
                                        onChange={e => setFormData({ ...formData, email: e.target.value })}
                                        className="w-full bg-zinc-50/50 border border-zinc-100 rounded-2xl py-4 pl-12 pr-4 outline-none focus:border-[#9d55ac] focus:bg-white transition-all text-zinc-900 font-medium placeholder:text-zinc-300"
                                    />
                                </div>
                            </div>

                            {/* Password */}
                            <div className="space-y-2">
                                <label className="text-xs font-bold text-zinc-400 uppercase tracking-widest ml-1">Password</label>
                                <div className="relative group">
                                    <Lock className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 group-focus-within:text-[#9d55ac] transition-colors" size={20} />
                                    <input
                                        type={showPassword ? "text" : "password"}
                                        required
                                        placeholder="••••••••"
                                        value={formData.password}
                                        onChange={e => setFormData({ ...formData, password: e.target.value })}
                                        className="w-full bg-zinc-50/50 border border-zinc-100 rounded-2xl py-4 pl-12 pr-12 outline-none focus:border-[#9d55ac] focus:bg-white transition-all text-zinc-900 font-medium placeholder:text-zinc-300"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowPassword(!showPassword)}
                                        className="absolute right-4 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 transition-colors"
                                    >
                                        {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                                    </button>
                                </div>
                            </div>

                            {error && (
                                <div className="bg-red-50 text-red-600 px-4 py-3 rounded-xl text-sm font-medium text-center">
                                    {error}
                                </div>
                            )}

                            <button
                                type="submit"
                                disabled={loading}
                                className="w-full bg-[#9d55ac] text-white rounded-2xl py-4 font-bold text-lg hover:bg-[#8a4a97] transition-all shadow-xl shadow-purple-500/20 flex items-center justify-center gap-2 group disabled:opacity-50"
                            >
                                {loading ? "Creating Account..." : "Get Started"}
                                {!loading && <ArrowRight size={20} className="group-hover:translate-x-1 transition-transform" />}
                            </button>

                            <div className="relative py-2">
                                <div className="absolute inset-0 flex items-center">
                                    <div className="w-full border-t border-zinc-100"></div>
                                </div>
                                <div className="relative flex justify-center text-xs uppercase">
                                    <span className="bg-white px-4 text-zinc-400 font-bold tracking-widest">Or continue with</span>
                                </div>
                            </div>

                            <button
                                type="button"
                                onClick={handleGoogleSignup}
                                className="w-full bg-white border border-zinc-200 text-zinc-700 rounded-2xl py-4 font-bold hover:bg-zinc-50 transition-all flex items-center justify-center gap-3 shadow-sm"
                            >
                                <svg className="w-5 h-5" viewBox="0 0 24 24">
                                    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
                                    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                                    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05" />
                                    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                                </svg>
                                Google
                            </button>
                        </form>

                        <p className="text-center mt-8 text-zinc-500 font-medium">
                            Already have an account?{" "}
                            <Link href="/auth/login" className="text-[#9d55ac] font-bold hover:underline decoration-2 underline-offset-4">
                                Sign In
                            </Link>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
