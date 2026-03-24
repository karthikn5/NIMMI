"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Mail, Lock, Eye, EyeOff, ArrowRight } from "lucide-react";
import Image from "next/image";

export default function Login() {
    const [formData, setFormData] = useState({ email: "", password: "" });
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const router = useRouter();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError("");
        try {
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email: formData.email, password: formData.password })
            });
            const data = await res.json();
            if (res.ok) {
                localStorage.setItem("nimmi_user_id", data.user_id);
                localStorage.setItem("nimmi_user_name", data.name || "");
                localStorage.setItem("nimmi_user_email", formData.email);
                router.push("/dashboard");
            } else {
                setError(data.detail || "Invalid email or password");
            }
        } catch {
            setError("Could not connect to backend");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-[#fcfcfd] flex items-center justify-center p-6 relative overflow-hidden">
            {/* Background Accents */}
            <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-400/5 blur-[120px] rounded-full" />
            <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-400/5 blur-[120px] rounded-full" />

            <div className="w-full max-w-md z-10">
                <div className="bg-white/40 backdrop-blur-2xl border border-white/40 rounded-[2.5rem] p-10 shadow-[0_20px_50px_rgba(0,0,0,0.05),inset_0_0_20px_rgba(255,255,255,0.5)] ring-1 ring-white/20">
                    <div className="text-center mb-10">
                        <div className="inline-flex items-center justify-center w-20 h-20 bg-white/50 rounded-3xl border border-white/60 shadow-inner mb-6 overflow-hidden relative">
                            <Image src="/nimmi-logo.png" alt="Nimmi Logo" fill className="object-contain p-3" />
                        </div>
                        <h1 className="text-3xl font-bold bg-gradient-to-b from-zinc-900 to-zinc-600 bg-clip-text text-transparent">Welcome Back</h1>
                        <p className="text-zinc-500 mt-2 font-medium">Log in to manage your AI assistants</p>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-6">
                        {/* Email */}
                        <div className="space-y-2">
                            <label className="text-xs font-bold text-zinc-400 uppercase tracking-widest ml-1">Email Address</label>
                            <div className="relative group">
                                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 group-focus-within:text-blue-500 transition-colors" size={20} />
                                <input
                                    type="email"
                                    required
                                    placeholder="name@example.com"
                                    value={formData.email}
                                    onChange={e => setFormData({ ...formData, email: e.target.value })}
                                    className="w-full bg-white/50 border border-white/60 rounded-2xl py-4 pl-12 pr-4 outline-none focus:border-blue-500 transition-all text-zinc-900 font-medium placeholder:text-zinc-300"
                                />
                            </div>
                        </div>

                        {/* Password */}
                        <div className="space-y-2">
                            <label className="text-xs font-bold text-zinc-400 uppercase tracking-widest ml-1">Password</label>
                            <div className="relative group">
                                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 group-focus-within:text-blue-500 transition-colors" size={20} />
                                <input
                                    type={showPassword ? "text" : "password"}
                                    required
                                    placeholder="••••••••"
                                    value={formData.password}
                                    onChange={e => setFormData({ ...formData, password: e.target.value })}
                                    className="w-full bg-white/50 border border-white/60 rounded-2xl py-4 pl-12 pr-12 outline-none focus:border-blue-500 transition-all text-zinc-900 font-medium placeholder:text-zinc-300"
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
                            <div className="bg-red-50/50 border border-red-100 text-red-600 px-4 py-3 rounded-xl text-sm font-medium text-center animate-shake">
                                {error}
                            </div>
                        )}

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full bg-blue-600 text-white rounded-2xl py-4 font-bold text-lg hover:bg-blue-700 transition-all shadow-xl shadow-blue-500/25 flex items-center justify-center gap-2 group disabled:opacity-50"
                        >
                            {loading ? "Verifying..." : "Log In"}
                            {!loading && <ArrowRight size={20} className="group-hover:translate-x-1 transition-transform" />}
                        </button>
                    </form>

                    <p className="text-center mt-8 text-zinc-500 font-medium">
                        Don&apos;t have an account?{" "}
                        <Link href="/auth/signup" className="text-blue-600 font-bold hover:underline decoration-2 underline-offset-4">
                            Sign Up
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    );
}
