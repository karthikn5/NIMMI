"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import AuthShell from "@/components/AuthShell";
import { Button, Input } from "@/components/ui";
import { apiBase, saveSession } from "@/lib/api";

export default function ResetPasswordPage() {
    return <Suspense><ResetPassword /></Suspense>;
}

function ResetPassword() {
    const token = useSearchParams().get("token") || "";
    const router = useRouter();
    const [password, setPassword] = useState("");
    const [confirm, setConfirm] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    const submit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (password !== confirm) return setError("The passwords don't match.");
        setBusy(true);
        setError("");
        try {
            const res = await fetch(`${apiBase()}/api/auth/reset-password`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token, new_password: password }),
            });
            const body = await res.json();
            if (!res.ok) throw new Error(body.detail || "Couldn't reset your password.");
            saveSession(body);
            router.push("/dashboard");
        } catch (err) {
            setError((err as Error).message);
            setBusy(false);
        }
    };

    if (!token) {
        return (
            <AuthShell title="This link isn't complete" description="Open the link from your email again, or request a new one.">
                <Link href="/auth/forgot-password"><Button variant="primary" className="w-full">Request a new link</Button></Link>
            </AuthShell>
        );
    }

    return (
        <AuthShell title="Set a new password" description="Use at least 8 characters. You'll be signed in afterwards.">
            <form onSubmit={submit} className="space-y-4">
                <div>
                    <label htmlFor="password" className="text-sm font-medium">New password</label>
                    <Input id="password" type="password" required minLength={8} autoFocus autoComplete="new-password" className="mt-1.5"
                           value={password} onChange={(e) => setPassword(e.target.value)} />
                </div>
                <div>
                    <label htmlFor="confirm" className="text-sm font-medium">Confirm password</label>
                    <Input id="confirm" type="password" required minLength={8} autoComplete="new-password" className="mt-1.5"
                           value={confirm} onChange={(e) => setConfirm(e.target.value)} />
                </div>
                {error && (
                    <p className="text-[13px] text-signal">
                        {error}{" "}
                        {error.includes("expired") && <Link href="/auth/forgot-password" className="underline underline-offset-2">Get a new link</Link>}
                    </p>
                )}
                <Button type="submit" variant="primary" className="w-full" disabled={busy}>{busy ? "Saving…" : "Save password"}</Button>
            </form>
        </AuthShell>
    );
}
