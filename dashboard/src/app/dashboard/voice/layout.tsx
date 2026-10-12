"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import AppHeader from "@/components/AppHeader";
import { ToastProvider, cn } from "@/components/ui";
import { currentUserId } from "@/lib/api";

const tabs = [
    { href: "/dashboard/voice", label: "Overview", exact: true },
    { href: "/dashboard/voice/agents", label: "Agents" },
    { href: "/dashboard/voice/calls", label: "Calls" },
    { href: "/dashboard/voice/campaigns", label: "Campaigns" },
    { href: "/dashboard/voice/data", label: "Collected data" },
    { href: "/dashboard/voice/numbers", label: "Numbers" },
    { href: "/dashboard/voice/compliance", label: "Compliance" },
];

export default function VoiceLayout({ children }: { children: ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();
    const [ready, setReady] = useState(false);

    useEffect(() => {
        if (!currentUserId()) router.push("/auth/signup");
        else setReady(true);
    }, [router]);

    return (
        <ToastProvider>
            <div className="min-h-screen bg-paper text-ink">
                <AppHeader />
                <div className="bg-white border-b border-line">
                    <div className="max-w-6xl mx-auto px-4 sm:px-6">
                        <div className="pt-7">
                            <h1 className="text-2xl font-semibold tracking-tight">Voice</h1>
                            <p className="text-sm text-stone-500 mt-1">Your assistants answer calls and call back new leads, in the language your customers speak.</p>
                        </div>

                        <nav aria-label="Voice sections" className="mt-5 -mb-px flex gap-6 overflow-x-auto [scrollbar-width:none]">
                            {tabs.map((t) => {
                                const active = t.exact ? pathname === t.href : pathname.startsWith(t.href);
                                return (
                                    <Link
                                        key={t.href}
                                        href={t.href}
                                        aria-current={active ? "page" : undefined}
                                        className={cn(
                                            "pb-3 text-sm border-b-2 whitespace-nowrap transition-colors",
                                            active ? "border-plum text-ink font-medium" : "border-transparent text-stone-500 hover:text-ink",
                                        )}
                                    >
                                        {t.label}
                                    </Link>
                                );
                            })}
                        </nav>
                    </div>
                </div>

                <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 pb-24">
                    {ready ? children : null}
                </main>
            </div>
        </ToastProvider>
    );
}
