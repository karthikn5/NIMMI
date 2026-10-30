"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import AppHeader from "@/components/AppHeader";
import { ToastProvider, cn } from "@/components/ui";
import { currentUserId } from "@/lib/api";
import { PlanNeeded, useLimits } from "@/lib/plan";
import { useRole } from "@/lib/whatsapp";

const tabs = [
    { href: "/dashboard/whatsapp", label: "Overview", exact: true },
    { href: "/dashboard/whatsapp/inbox", label: "Inbox" },
    { href: "/dashboard/whatsapp/assistant", label: "Assistant", managers: true },
    { href: "/dashboard/whatsapp/files", label: "Files" },
    { href: "/dashboard/whatsapp/settings", label: "Settings", managers: true },
];

export default function WhatsAppLayout({ children }: { children: ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();
    const [ready, setReady] = useState(false);
    const limits = useLimits();
    const role = useRole();

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
                            <h1 className="text-2xl font-semibold tracking-tight">WhatsApp</h1>
                            <p className="text-sm text-stone-500 mt-1">
                                Your assistant answers customers on your WhatsApp number the way a person on your team would. Your team can step in at any time.
                            </p>
                        </div>
                        <nav aria-label="WhatsApp sections" className="mt-5 -mb-px flex gap-6 overflow-x-auto [scrollbar-width:none]">
                            {tabs.filter((t) => !t.managers || role !== "agent").map((t) => {
                                const active = t.exact ? pathname === t.href : pathname.startsWith(t.href);
                                return (
                                    <Link key={t.href} href={t.href} data-agent={`whatsapp.tab.${t.href.split("/")[3] ?? "overview"}`} aria-current={active ? "page" : undefined}
                                          className={cn("pb-3 text-sm border-b-2 whitespace-nowrap transition-colors",
                                              active ? "border-plum text-ink font-medium" : "border-transparent text-stone-500 hover:text-ink")}>
                                        {t.label}
                                    </Link>
                                );
                            })}
                        </nav>
                    </div>
                </div>
                <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 pb-24">
                    {limits?.includes && !limits.includes.whatsapp && (
                        <PlanNeeded feature="whatsapp">
                            Look around and get your files ready. Connecting a number and answering on WhatsApp come with Growth or
                            Pro for one of your assistants.
                        </PlanNeeded>
                    )}
                    {ready ? children : null}
                </main>
            </div>
        </ToastProvider>
    );
}
