"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import AppHeader from "@/components/AppHeader";
import { EmptyState, ToastProvider, cn } from "@/components/ui";
import { currentUserId } from "@/lib/api";
import { DRAFTS_CHANGED, type Drafts, type Threads } from "@/lib/email";
import { PlanNeeded, useLimits } from "@/lib/plan";
import { useApi } from "@/lib/useApi";
import { useRole } from "@/lib/whatsapp";

const tabs = [
    { href: "/dashboard/email", label: "Overview", exact: true },
    { href: "/dashboard/email/inbox", label: "Inbox" },
    { href: "/dashboard/email/automations", label: "Automations" },
    { href: "/dashboard/email/journeys", label: "Journeys" },
    { href: "/dashboard/email/board", label: "Lead board" },
    { href: "/dashboard/email/drafts", label: "Drafts" },
    { href: "/dashboard/email/leads", label: "Lead sources" },
    { href: "/dashboard/email/bulk", label: "Bulk email" },
    { href: "/dashboard/email/reports", label: "Reports" },
    { href: "/dashboard/email/history", label: "History" },
    { href: "/dashboard/email/settings", label: "Settings" },
];

export default function EmailLayout({ children }: { children: ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();
    const [ready, setReady] = useState(false);
    const limits = useLimits();
    const role = useRole();
    const drafts = useApi<Drafts>(ready && role && role !== "agent" ? "/api/email/drafts?limit=1" : null);
    const inbox = useApi<Threads>(ready && role && role !== "agent" ? "/api/email/inbox?limit=1" : null);
    const { reload } = drafts;
    const { reload: reloadInbox } = inbox;

    useEffect(() => {
        if (!currentUserId()) router.push("/auth/signup");
        else setReady(true);
    }, [router]);

    useEffect(() => {
        const again = () => { void reload(); void reloadInbox(); };
        window.addEventListener(DRAFTS_CHANGED, again);
        return () => window.removeEventListener(DRAFTS_CHANGED, again);
    }, [reload, reloadInbox]);

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
                                        {t.label === "Drafts" && !!(drafts.data?.total || drafts.data?.agent) && (
                                            <span className="ml-1.5 text-xs text-plum" aria-label={`, ${(drafts.data?.total ?? 0) + (drafts.data?.agent ?? 0)} waiting`}>{(drafts.data?.total ?? 0) + (drafts.data?.agent ?? 0)}</span>
                                        )}
                                        {t.label === "Inbox" && !!inbox.data?.unread && (
                                            <span className="ml-1.5 text-xs text-plum" aria-label={`, ${inbox.data.unread} unread`}>{inbox.data.unread}</span>
                                        )}
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
                            {limits?.includes && !limits.includes.team_alerts && (
                                <PlanNeeded feature="team_alerts">
                                    Look around and get your emails ready. Alerts to your team and a welcome email come with Starter, the rest
                                    with Growth or Pro, for one of your assistants.
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
