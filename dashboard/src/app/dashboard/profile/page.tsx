"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AppHeader from "@/components/AppHeader";
import { Button, Card, Input, SettingRow, Skeleton, ToastProvider, useToast } from "@/components/ui";
import { apiJson, clearSession, currentUserId } from "@/lib/api";
import { formatDate } from "@/lib/voice/api";

type Profile = { user_id: string; email: string; name: string; has_password: boolean; created_at: string | null };

export default function ProfilePage() {
    return (
        <ToastProvider>
            <ProfileView />
        </ToastProvider>
    );
}

function ProfileView() {
    const router = useRouter();
    const toast = useToast();
    const [profile, setProfile] = useState<Profile | null>(null);
    const [form, setForm] = useState({ name: "", email: "" });
    const [saving, setSaving] = useState(false);
    const [pw, setPw] = useState({ current: "", next: "" });
    const [changing, setChanging] = useState(false);

    useEffect(() => {
        if (!currentUserId()) {
            router.push("/auth/login");
            return;
        }
        apiJson<Profile>("/api/auth/profile")
            .then((p) => { setProfile(p); setForm({ name: p.name, email: p.email }); })
            .catch((e) => toast((e as Error).message));
    }, [router, toast]);

    const dirty = profile && (form.name !== profile.name || form.email !== profile.email);

    const save = async (e: React.FormEvent) => {
        e.preventDefault();
        setSaving(true);
        try {
            const res = await apiJson<{ name: string; email: string }>("/api/auth/profile", { method: "PATCH", json: form });
            setProfile((p) => (p ? { ...p, ...res } : p));
            try {
                localStorage.setItem("nimmi_user_name", res.name);
                localStorage.setItem("nimmi_user_email", res.email);
            } catch { /* storage blocked */ }
            toast("Saved");
        } catch (err) {
            toast((err as Error).message);
        } finally {
            setSaving(false);
        }
    };

    const changePassword = async (e: React.FormEvent) => {
        e.preventDefault();
        setChanging(true);
        try {
            await apiJson("/api/auth/change-password", { method: "POST", json: { current_password: pw.current, new_password: pw.next } });
            setPw({ current: "", next: "" });
            setProfile((p) => (p ? { ...p, has_password: true } : p));
            toast("Password changed");
        } catch (err) {
            toast((err as Error).message);
        } finally {
            setChanging(false);
        }
    };

    const signOut = () => {
        clearSession();
        router.push("/auth/login");
    };

    return (
        <div className="min-h-screen bg-paper text-ink">
            <AppHeader userName={profile?.name} />
            <main className="max-w-3xl mx-auto px-4 sm:px-6 py-8 pb-24">
                <h1 className="text-2xl font-semibold tracking-tight">Profile</h1>
                <p className="text-sm text-stone-500 mt-1">
                    {profile?.created_at ? `Member since ${formatDate(profile.created_at)}.` : "Your account details."}
                </p>

                {!profile ? <Skeleton className="h-64 mt-8" /> : (
                    <>
                        <form onSubmit={save}>
                            <Card className="px-5 py-1 mt-8">
                                <SettingRow label="Name" htmlFor="name">
                                    <Input id="name" autoComplete="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                                </SettingRow>
                                <SettingRow label="Email" htmlFor="email" hint="You sign in with this email. Lead alerts go here unless you set another address in Integrations.">
                                    <Input id="email" type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
                                </SettingRow>
                            </Card>
                            <div className="flex justify-end mt-3">
                                <Button type="submit" variant="primary" disabled={!dirty || saving}>{saving ? "Saving…" : "Save changes"}</Button>
                            </div>
                        </form>

                        <form onSubmit={changePassword} className="mt-10">
                            <h2 className="text-[15px] font-semibold mb-4">{profile.has_password ? "Change password" : "Set a password"}</h2>
                            <Card className="px-5 py-1">
                                {profile.has_password && (
                                    <SettingRow label="Current password" htmlFor="current">
                                        <Input id="current" type="password" autoComplete="current-password" required
                                               value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} />
                                    </SettingRow>
                                )}
                                <SettingRow label="New password" htmlFor="new" hint={profile.has_password ? "At least 8 characters." : "You signed up with Google. A password lets you sign in with your email too."}>
                                    <Input id="new" type="password" autoComplete="new-password" required minLength={8}
                                           value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} />
                                </SettingRow>
                            </Card>
                            <div className="flex justify-end mt-3">
                                <Button type="submit" disabled={changing || pw.next.length < 8}>{changing ? "Saving…" : "Update password"}</Button>
                            </div>
                        </form>

                        <div className="mt-10 flex items-center justify-between gap-4 px-5 py-4 bg-white border border-line rounded-lg">
                            <div>
                                <p className="text-sm font-medium">Sign out</p>
                                <p className="text-[13px] text-stone-500 mt-0.5">Signs you out on this browser.</p>
                            </div>
                            <Button onClick={signOut}>Sign out</Button>
                        </div>
                    </>
                )}
            </main>
        </div>
    );
}
