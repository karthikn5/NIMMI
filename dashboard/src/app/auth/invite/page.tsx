"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import AuthShell from "@/components/AuthShell";
import { Button } from "@/components/ui";
import { apiJson, currentUserId, setWorkspace } from "@/lib/api";

export default function InvitePage() {
    return <Suspense><Invite /></Suspense>;
}

function Invite() {
    const token = useSearchParams().get("token") || "";
    const router = useRouter();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [signedIn, setSignedIn] = useState(false);
    useEffect(() => setSignedIn(!!currentUserId()), []);
    const here = `/auth/invite?token=${encodeURIComponent(token)}`;

    const accept = async () => {
        setBusy(true);
        setError("");
        try {
            const res = await apiJson<{ owner_id: string }>("/api/team/accept", { method: "POST", json: { token } });
            setWorkspace(res.owner_id);
            router.push("/dashboard");
        } catch (e) {
            setError((e as Error).message);
            setBusy(false);
        }
    };

    return (
        <AuthShell
            title="Join a team on Nimmi AI"
            description="You've been invited to help manage a workspace: its assistants, live chats and calls."
        >
            {signedIn ? (
                <>
                    <Button variant="primary" className="w-full" onClick={accept} disabled={busy || !token}>
                        {busy ? "Joining…" : "Accept invite"}
                    </Button>
                    {error && <p className="text-[13px] text-signal mt-3">{error}</p>}
                </>
            ) : (
                <div className="space-y-2">
                    <p className="text-[13px] text-stone-600 mb-4">Sign in or create an account with the email the invite was sent to.</p>
                    <Link href={`/auth/signup?next=${encodeURIComponent(here)}`}><Button variant="primary" className="w-full">Create an account</Button></Link>
                    <Link href={`/auth/login?next=${encodeURIComponent(here)}`}><Button className="w-full">I already have an account</Button></Link>
                </div>
            )}
        </AuthShell>
    );
}
