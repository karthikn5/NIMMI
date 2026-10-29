"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ChevronDown } from "lucide-react";
import AppHeader from "@/components/AppHeader";
import { ToastProvider, cn } from "@/components/ui";
import { currentUserId } from "@/lib/api";
import { PaidOnly, useLimits } from "@/lib/plan";
import { useApi } from "@/lib/useApi";
import { SCHEDULE_CHANGED } from "@/lib/voice/schedule";
import type { ScheduleAttention } from "@/lib/voice/types";

type Tab = { href: string; label: string; exact?: boolean; menu?: { href: string; label: string; hint: string }[] };

const tabs: Tab[] = [
    { href: "/dashboard/voice", label: "Overview", exact: true },
    {
        href: "/dashboard/voice/agents", label: "Agents", menu: [
            { href: "/dashboard/voice/agents?direction=inbound", label: "Incoming calls", hint: "Answers people who call your number" },
            { href: "/dashboard/voice/agents?direction=outbound", label: "Outgoing calls", hint: "Calls people back, and runs campaigns" },
        ],
    },
    { href: "/dashboard/voice/knowledge", label: "Knowledge" },
    { href: "/dashboard/voice/contacts", label: "Contacts" },
    { href: "/dashboard/voice/calls", label: "Calls" },
    { href: "/dashboard/voice/schedule", label: "Schedule" },
    { href: "/dashboard/voice/campaigns", label: "Campaigns" },
    { href: "/dashboard/voice/data", label: "Collected data" },
    { href: "/dashboard/voice/numbers", label: "Numbers" },
    { href: "/dashboard/voice/compliance", label: "Compliance" },
];

export default function VoiceLayout({ children }: { children: ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();
    const [ready, setReady] = useState(false);
    const limits = useLimits();
    // What waits for the team in Schedule (meetings to approve, follow-ups to check...), checked on each page change.
    const attention = useApi<ScheduleAttention>(ready ? "/api/voice/schedule/attention" : null);
    const reloadAttention = attention.reload;

    useEffect(() => {
        if (!currentUserId()) router.push("/auth/signup");
        else setReady(true);
    }, [router]);
    useEffect(() => { reloadAttention(); }, [pathname, reloadAttention]);
    useEffect(() => {
        window.addEventListener(SCHEDULE_CHANGED, reloadAttention);
        return () => window.removeEventListener(SCHEDULE_CHANGED, reloadAttention);
    }, [reloadAttention]);

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
                                if (t.menu) return <MenuTab key={t.href} tab={t} active={active} />;
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
                                        {t.href === "/dashboard/voice/schedule" && (attention.data?.total ?? 0) > 0 && (
                                            <span aria-label={`, ${attention.data!.total} waiting for you`}
                                                  className="ml-1.5 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-plum text-white text-[11px] font-medium tabular-nums align-[1px]">
                                                {attention.data!.total}
                                            </span>
                                        )}
                                    </Link>
                                );
                            })}
                        </nav>
                    </div>
                </div>

                <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 pb-24">
                    {limits && !limits.voice && (
                        <PaidOnly feature="Voice calls">
                            Look around and set up your agents. Turning on calls, test calls, numbers and campaigns needs a plan for one of your assistants.
                        </PaidOnly>
                    )}
                    {ready ? children : null}
                </main>
            </div>
        </ToastProvider>
    );
}

/** A tab with a small menu: opens on hover, and on click or keyboard (phones have no hover). The tab row scrolls
 * sideways on small screens, so the menu is placed on the page rather than inside the row, where it would be cut off. */
function MenuTab({ tab, active }: { tab: Tab; active: boolean }) {
    const [at, setAt] = useState<{ left: number; top: number } | null>(null);
    const box = useRef<HTMLDivElement>(null);
    const closing = useRef<ReturnType<typeof setTimeout> | null>(null);
    const open = () => {
        if (closing.current) clearTimeout(closing.current);
        const r = box.current?.getBoundingClientRect();
        if (r) setAt({ left: r.left, top: r.bottom });
    };
    const close = (soon = false) => {
        if (closing.current) clearTimeout(closing.current);
        if (soon) closing.current = setTimeout(() => setAt(null), 150);
        else setAt(null);
    };
    useEffect(() => {
        if (!at) return;
        const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
        const onAway = (e: MouseEvent) => { if (!box.current?.parentElement?.contains(e.target as Node)) close(); };
        const onMove = () => close();
        window.addEventListener("keydown", onKey);
        window.addEventListener("mousedown", onAway);
        window.addEventListener("scroll", onMove, true);
        window.addEventListener("resize", onMove);
        return () => {
            window.removeEventListener("keydown", onKey);
            window.removeEventListener("mousedown", onAway);
            window.removeEventListener("scroll", onMove, true);
            window.removeEventListener("resize", onMove);
        };
    }, [at]);

    return (
        <div onMouseEnter={open} onMouseLeave={() => close(true)}>
            <div
                ref={box}
                className={cn(
                    "flex items-center gap-1 pb-3 text-sm border-b-2 whitespace-nowrap transition-colors",
                    active ? "border-plum text-ink font-medium" : "border-transparent text-stone-500 hover:text-ink",
                )}
            >
                <Link href={tab.href} aria-current={active ? "page" : undefined} onClick={() => close()}>{tab.label}</Link>
                <button
                    type="button"
                    aria-label={`${tab.label}: choose`}
                    aria-haspopup="menu"
                    aria-expanded={!!at}
                    onClick={() => (at ? close() : open())}
                    className="p-0.5 -m-0.5 rounded text-stone-400 hover:text-ink focus-visible:outline-2 focus-visible:outline-plum"
                >
                    <ChevronDown size={14} aria-hidden />
                </button>
            </div>
            {at && (
                <div
                    role="menu"
                    style={{ position: "fixed", left: at.left, top: at.top }}
                    onMouseEnter={open}
                    onMouseLeave={() => close(true)}
                    className="z-50 mt-1 w-64 p-1 bg-white border border-line rounded-md shadow-[0_8px_30px_rgba(28,23,25,0.12)]"
                >
                    {tab.menu?.map((m) => (
                        <Link key={m.href} href={m.href} role="menuitem" onClick={() => close()}
                              className="block px-3 py-2 rounded hover:bg-stone-50 focus-visible:outline-2 focus-visible:outline-plum">
                            <span className="block text-sm text-ink">{m.label}</span>
                            <span className="block text-xs text-stone-500 mt-0.5">{m.hint}</span>
                        </Link>
                    ))}
                </div>
            )}
        </div>
    );
}
