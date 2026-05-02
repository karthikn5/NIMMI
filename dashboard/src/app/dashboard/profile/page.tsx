"use client";

import { Bot, User, Mail, Save, LogOut, ArrowLeft, Crown } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

interface UserProfile {
    user_id: string;
    email: string;
    name: string;
    subscription_tier: string;
    created_at: string | null;
}

export default function Profile() {
    const [profile, setProfile] = useState<UserProfile | null>(null);
    const [formData, setFormData] = useState({ name: "", email: "" });
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const [success, setSuccess] = useState("");
    const router = useRouter();

    useEffect(() => {
        const userId = localStorage.getItem("nimmi_user_id");
        if (!userId) {
            router.push("/auth/login");
            return;
        }

        const fetchProfile = async () => {
            try {
                const apiUrl = typeof window !== "undefined" && window.location.hostname.includes("nimmiai.in")
                    ? "https://api.nimmiai.in"
                    : (process.env.NEXT_PUBLIC_API_URL || "https://api.nimmiai.in");
                const res = await fetch(`${apiUrl}/api/auth/profile?user_id=${userId}`);
                const data = await res.json();
                if (res.ok) {
                    setProfile(data);
                    setFormData({ name: data.name, email: data.email });
                } else {
                    setError(data.detail || "Failed to load profile");
                }
            } catch (err) {
                setError("Could not connect to backend");
            } finally {
                setLoading(false);
            }
        };

        fetchProfile();
    }, [router]);

    const handleSave = async () => {
        const userId = localStorage.getItem("nimmi_user_id");
        setSaving(true);
        setError("");
        setSuccess("");

        try {
            const apiUrl = typeof window !== "undefined" && window.location.hostname.includes("nimmiai.in")
                ? "https://api.nimmiai.in"
                : (process.env.NEXT_PUBLIC_API_URL || "https://api.nimmiai.in");
            const res = await fetch(`${apiUrl}/api/auth/profile?user_id=${userId}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: formData.name,
                    email: formData.email
                })
            });

            const data = await res.json();

            if (res.ok) {
                setSuccess("Profile updated successfully!");
                localStorage.setItem("nimmi_user_name", formData.name);
                // Update profile state
                setProfile(prev => prev ? { ...prev, name: formData.name, email: formData.email } : null);
            } else {
                setError(data.detail || "Failed to update profile");
            }
        } catch (err) {
            setError("Could not connect to backend");
        } finally {
            setSaving(false);
        }
    };

    const handleLogout = () => {
        localStorage.removeItem("nimmi_user_id");
        localStorage.removeItem("nimmi_user_name");
        router.push("/auth/login");
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-[#050505] flex items-center justify-center text-white">
                <div className="text-white/50">Loading profile...</div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[#050505] text-white p-6">
            <div className="max-w-2xl mx-auto">
                {/* Header */}
                <div className="flex items-center gap-4 mb-10">
                    <Link href="/dashboard" className="p-3 bg-white/5 rounded-xl hover:bg-white/10 transition-colors">
                        <ArrowLeft size={20} />
                    </Link>
                    <div>
                        <h1 className="text-3xl font-bold">Profile Settings</h1>
                        <p className="text-white/50 mt-1">Manage your account details</p>
                    </div>
                </div>

                {/* Profile Card */}
                <div className="bg-zinc-900/50 border border-white/10 rounded-3xl p-8 backdrop-blur-xl">
                    {/* Avatar Section */}
                    <div className="flex items-center gap-6 mb-10 pb-8 border-b border-white/10">
                        <div className="w-20 h-20 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl flex items-center justify-center text-3xl font-bold">
                            {formData.name ? formData.name[0].toUpperCase() : "U"}
                        </div>
                        <div>
                            <h2 className="text-2xl font-bold">{formData.name || "User"}</h2>
                            <div className="flex items-center gap-2 mt-2">
                                <Crown size={16} className="text-yellow-500" />
                                <span className="text-white/60 text-sm">{profile?.subscription_tier || "Free"} Plan</span>
                            </div>
                        </div>
                    </div>

                    {/* Messages */}
                    {error && (
                        <div className="bg-red-500/10 border border-red-500/20 text-red-500 p-4 rounded-xl text-sm mb-6">
                            {error}
                        </div>
                    )}
                    {success && (
                        <div className="bg-green-500/10 border border-green-500/20 text-green-500 p-4 rounded-xl text-sm mb-6">
                            {success}
                        </div>
                    )}

                    {/* Form */}
                    <div className="space-y-6">
                        <div className="space-y-2">
                            <label className="text-sm font-bold text-white/50 uppercase tracking-widest pl-1">Full Name</label>
                            <div className="relative">
                                <User className="absolute left-4 top-1/2 -translate-y-1/2 text-white/20" size={20} />
                                <input
                                    type="text"
                                    value={formData.name}
                                    onChange={e => setFormData({ ...formData, name: e.target.value })}
                                    placeholder="Your name"
                                    className="w-full bg-white/5 border border-white/10 rounded-2xl py-4 pl-12 pr-4 outline-none focus:border-blue-500 transition-all font-medium"
                                />
                            </div>
                        </div>

                        <div className="space-y-2">
                            <label className="text-sm font-bold text-white/50 uppercase tracking-widest pl-1">Email Address</label>
                            <div className="relative">
                                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 text-white/20" size={20} />
                                <input
                                    type="email"
                                    value={formData.email}
                                    onChange={e => setFormData({ ...formData, email: e.target.value })}
                                    placeholder="your@email.com"
                                    className="w-full bg-white/5 border border-white/10 rounded-2xl py-4 pl-12 pr-4 outline-none focus:border-blue-500 transition-all font-medium"
                                />
                            </div>
                        </div>

                        {/* Member Since */}
                        {profile?.created_at && (
                            <div className="pt-4 text-sm text-white/40">
                                Member since {new Date(profile.created_at).toLocaleDateString('en-US', {
                                    year: 'numeric',
                                    month: 'long',
                                    day: 'numeric'
                                })}
                            </div>
                        )}
                    </div>

                    {/* Actions */}
                    <div className="flex gap-4 mt-10">
                        <button
                            onClick={handleSave}
                            disabled={saving}
                            className="flex-1 py-4 bg-blue-600 rounded-2xl font-bold hover:bg-blue-500 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
                        >
                            <Save size={20} />
                            {saving ? "Saving..." : "Save Changes"}
                        </button>
                        <button
                            onClick={handleLogout}
                            className="px-6 py-4 bg-red-500/10 border border-red-500/20 text-red-500 rounded-2xl font-bold hover:bg-red-500/20 transition-all flex items-center gap-2"
                        >
                            <LogOut size={20} />
                            Logout
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
