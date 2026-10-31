"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import AppHeader from "@/components/AppHeader";
import { EmptyState, ToastProvider, cn } from "@/components/ui";
import { currentUserId } from "@/lib/api";
import { PlanNeeded, useLimits } from "@/lib/plan";
import { useRole } from "@/lib/whatsapp";

const tabs = [
    { href: "/dashboard/email", label: "Overview", exact: true },
    { href: "/dashboard/email/automations", label: "Automations" },
    { href: "/dashboard/email/bulk", label: "Bulk email" },
    { href: "/dashboard/email/history", label: "History" },
    { href: "/dashboard/email/settings", label: "Settings" },
];

export default function EmailLayout({ children }: { children: ReactNode }) {
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
                            <h1 className="text-2xl font-semibold tracking-tight">Email</h1>
                            <p className="text-sm text-stone-500 mt-1">
                                Alerts to your team, and emails to the people who contact your business: after a chat or a call, in bulk, from your own domain.
                            </p>
                        </div>
                        <nav aria-label="Email sections" className="mt-5 -mb-px flex gap-6 overflow-x-auto [scrollbar-width:none]">
                            {tabs.map((t) => {
                                const active = t.exact ? pathname === t.href : pathname.startsWith(t.href);
                                return (
                                    <Link key={t.href} href={t.href} data-agent={`email.tab.${t.href.split("/")[3] ?? "overview"}`} aria-current={active ? "page" : undefined}
                                          className={cn("pb-3 text-sm border-b-2 whitespace-nowrap transition-colors",
                                              active ? "border-plum text-ink font-medium" : "border-transparent text-stone-500 hover:text-ink")}>
                                        {t.label}
                                    </Link>
                                );
                            })}
                        </nav>
                    </div>
                </div>
                <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 pb-28">
                    {role === "agent" ? (
                        <EmptyState title="Email is set up by your workspace's owner and admins" body="Ask them to change alerts, automatic emails or bulk email." />
                    ) : (
                        <>
                            {limits?.includes && !limits.includes.email_alerts && (
                                <PlanNeeded feature="email_alerts">
                                    Look around and get your emails ready. Alerts to your team and emails to customers come with Growth or Pro for
                                    one of your assistants.
                                </PlanNeeded>
                            )}
                            {ready ? children : null}
                        </>
                    )}
                </main>
            </div>
        </ToastProvider>
    );
}
