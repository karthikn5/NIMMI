"use client";

import { useState } from "react";
import Link from "next/link";
import AuthShell from "@/components/AuthShell";
import { Button, Input } from "@/components/ui";
import { apiBase } from "@/lib/api";

export default function ForgotPasswordPage() {
    const [email, setEmail] = useState("");
    const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
    const [error, setError] = useState("");

    const submit = async (e: React.FormEvent) => {
        e.preventDefault();
        setState("sending");
        try {
            const res = await fetch(`${apiBase()}/api/auth/forgot-password`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email }),
            });
            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                throw new Error(body.detail || "Something went wrong. Try again.");
            }
            setState("sent");
        } catch (err) {
            setError((err as Error).message);
            setState("error");
        }
    };

    return (
        <AuthShell
            title="Reset your password"
            description="Enter the email you sign in with. We'll send a link to set a new password."
            footer={<Link href="/auth/login" className="text-plum hover:underline underline-offset-4">Back to sign in</Link>}
        >
            {state === "sent" ? (
                <p className="text-sm leading-relaxed">
                    If <span className="font-medium">{email}</span> has an account, a reset link is on its way. It works for one hour.
                    Check your spam folder if it doesn&apos;t arrive in a few minutes.
                </p>
            ) : (
                <form onSubmit={submit} className="space-y-4">
                    <div>
                        <label htmlFor="email" className="text-sm font-medium">Email</label>
                        <Input id="email" type="email" required autoFocus autoComplete="email" className="mt-1.5"
                               value={email} onChange={(e) => setEmail(e.target.value)} />
                    </div>
                    {state === "error" && <p className="text-[13px] text-signal">{error}</p>}
                    <Button type="submit" variant="primary" className="w-full" disabled={state === "sending"}>
                        {state === "sending" ? "Sending…" : "Send reset link"}
                    </Button>
                </form>
            )}
        </AuthShell>
    );
}
