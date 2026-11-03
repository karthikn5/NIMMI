"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import AppHeader from "@/components/AppHeader";
import { ToastProvider, cn } from "@/components/ui";
import { currentUserId } from "@/lib/api";
import { useRole } from "@/lib/whatsapp";

const tabs = [
    { href: "/dashboard/leads", label: "Needs attention", exact: true },
    { href: "/dashboard/leads/all", label: "All leads" },
    { href: "/dashboard/leads/board", label: "Board", manager: true },
    { href: "/dashboard/leads/sources", label: "Sources", manager: true },
    { href: "/dashboard/leads/reports", label: "Reports" },
];

export default function LeadsLayout({ children }: { children: ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();
    const role = useRole();
    const [ready, setReady] = useState(false);
    useEffect(() => {
        if (!currentUserId()) router.push("/auth/signup");
        else setReady(true);
    }, [router]);
    const inTab = tabs.some((t) => (t.exact ? pathname === t.href : pathname.startsWith(t.href)));
    return (
        <ToastProvider>
            <div className="min-h-screen bg-paper text-ink">
                <AppHeader />
                <div className="bg-white border-b border-line">
                    <div className="max-w-6xl mx-auto px-4 sm:px-6">
                        <div className="pt-7">
                            <h1 className="text-2xl font-semibold tracking-tight">Leads</h1>
                            <p className="text-sm text-stone-500 mt-1">Everyone who asked, from every place: who looks after them, what happens next, and how it ended.</p>
                        </div>
                        <nav aria-label="Leads sections" className="mt-5 -mb-px flex gap-6 overflow-x-auto [scrollbar-width:none]">
                            {tabs.filter((t) => !t.manager || role !== "agent").map((t) => {
                                const active = t.exact ? pathname === t.href : pathname.startsWith(t.href);
                                return (
                                    <Link key={t.href} href={t.href} data-agent={`leads.tab.${t.href.split("/")[3] ?? "attention"}`} aria-current={active ? "page" : undefined}
                                          className={cn("pb-3 text-sm border-b-2 whitespace-nowrap transition-colors", active ? "border-plum text-ink font-medium" : "border-transparent text-stone-500 hover:text-ink")}>
                                        {t.label}
                                    </Link>
                                );
                            })}
                            {!inTab && <span className="pb-3 text-sm border-b-2 border-plum text-ink font-medium whitespace-nowrap" aria-current="page">One lead</span>}
                        </nav>
                    </div>
                </div>
                <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 pb-28">{ready ? children : null}</main>
            </div>
        </ToastProvider>
    );
}
