"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { createClient } from "@/utils/supabase/client";
import { apiUrl, saveSession } from "@/lib/api";

/** Where to go after signing in: the page that sent you here, or the dashboard. */
export function nextPath() {
    // Only paths on this site: "/\evil.com" and "//evil.com" both leave it, so resolve and compare origins.
    let saved: string | null = null;
    try { saved = sessionStorage.getItem(NEXT_KEY); } catch { /* storage blocked */ }
    const next = new URLSearchParams(window.location.search).get("next") || saved;
    if (!next || !next.startsWith("/")) return "/dashboard";
    try {
        const url = new URL(next, window.location.origin);
        return url.origin === window.location.origin ? url.pathname + url.search + url.hash : "/dashboard";
    } catch {
        return "/dashboard";
    }
}

const NEXT_KEY = "nimmi_next_after_google";

/** Send the browser to Google. It comes back to `returnPath` exactly as listed in Supabase's redirect URLs
 *  (no query string), so the page to open afterwards is remembered in this tab instead. */
export async function startGoogleSignIn(returnPath: "/auth/login" | "/auth/signup") {
    const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || window.location.origin;
    const next = new URLSearchParams(window.location.search).get("next");
    try { if (next) sessionStorage.setItem(NEXT_KEY, next); else sessionStorage.removeItem(NEXT_KEY); } catch { /* storage blocked */ }
    await createClient().auth.signInWithOAuth({ provider: "google", options: { redirectTo: `${siteUrl}${returnPath}` } });
}

/**
 * Finishes Google sign-in when the browser has just come back from Google (and only then):
 * Supabase's session is exchanged for a Nimmi session, the dashboard is loaded meanwhile, and
 * Supabase's own copy is dropped so "Sign out" really signs out.
 */
export function useGoogleReturn() {
    const router = useRouter();
    const [finishing, setFinishing] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        const query = new URLSearchParams(window.location.search);
        const hash = new URLSearchParams(window.location.hash.slice(1));
        const failed = query.get("error_description") || hash.get("error_description");
        if (failed) {
            setError(`Google sign-in didn't finish (${failed.replace(/\+/g, " ")}). Please try again.`);
            return;
        }
        if (!query.get("code") && !hash.get("access_token")) return; // an ordinary visit to the page
        setFinishing(true);
        const next = nextPath();
        router.prefetch(next);

        const supabase = createClient();
        const forget = () => supabase.auth.signOut({ scope: "local" }).catch(() => undefined);
        (async () => {
            try {
                const { data: { session } } = await supabase.auth.getSession(); // exchanges Google's code
                if (!session) throw new Error("Google sign-in expired. Please try again.");
                const meta = session.user.user_metadata || {};
                const res = await fetch(apiUrl("/api/auth/social"), {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ access_token: session.access_token, name: meta.full_name || meta.name || "" }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || !data.token) {
                    throw new Error(data.detail || "Google sign-in didn't work. Please try again, or use your email and password.");
                }
                saveSession(data);
                try { sessionStorage.removeItem(NEXT_KEY); } catch { /* storage blocked */ }
                forget();
                router.replace(next);
            } catch (e) {
                forget();
                setFinishing(false);
                setError(e instanceof TypeError
                    ? "Couldn't reach Nimmi to finish Google sign-in. Check your connection and try again."
                    : (e as Error).message);
                window.history.replaceState(null, "", window.location.pathname); // so a refresh doesn't retry a used code
            }
        })();
    }, [router]);

    return { finishing, error };
}

/** Shown instead of the form while Google sign-in finishes, so it never looks like nothing happened. */
export function GoogleFinishing() {
    return (
        <div className="min-h-screen flex items-center justify-center bg-[#fbfaff] px-4" role="status" aria-live="polite">
            <div className="w-full max-w-sm bg-white border border-purple-100 rounded-[28px] shadow-[0_20px_60px_-24px_rgba(85,10,100,0.25)] px-8 py-10 text-center">
                <Image src="/favicon.png" alt="" width={40} height={40} className="mx-auto" priority />
                <div className="mt-6 mx-auto h-9 w-9 rounded-full border-[3px] border-purple-100 border-t-[#9b51b4] animate-spin" aria-hidden />
                <p className="mt-5 text-[17px] font-semibold text-slate-900">Signing you in with Google</p>
                <p className="mt-1.5 text-sm text-slate-500">Opening your dashboard. This takes a moment.</p>
            </div>
        </div>
    );
}
