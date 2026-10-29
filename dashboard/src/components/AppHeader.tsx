"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/components/ui";
import { activeOwnerId, apiJson, clearSession, getWorkspace, setWorkspace } from "@/lib/api";
import { useWaitingCount } from "@/lib/liveChat";
import AgentToggle from "@/components/agent/AgentToggle";

const nav = [
    { href: "/dashboard", label: "Assistants", exact: true },
    { href: "/dashboard/deployments", label: "Deployments", managerOnly: true },
    { href: "/dashboard/live-chat", label: "Live chat" },
    { href: "/dashboard/questions", label: "Questions", managerOnly: true },
    { href: "/dashboard/voice", label: "Voice" },
    { href: "/dashboard/whatsapp", label: "WhatsApp" },
    { href: "/dashboard/integrations", label: "Integrations", managerOnly: true }, // agents can't change settings
    { href: "/dashboard/analytics", label: "Analytics" },
    { href: "/dashboard/billing", label: "Billing", ownerOnly: true },
] as { href: string; label: string; exact?: boolean; ownerOnly?: boolean; managerOnly?: boolean }[];

type Workspace = { owner_id: string; name: string; role: "owner" | "admin" | "agent" };

/** Top bar shared by dashboard screens. */
export default function AppHeader({ userName }: { userName?: string }) {
    const pathname = usePathname();
    const router = useRouter();
    const waiting = useWaitingCount();
    const [name, setName] = useState("");
    const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
    const [menu, setMenu] = useState(false);
    const [inOtherWorkspace, setInOtherWorkspace] = useState(false);
    const menuRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        try { setName(localStorage.getItem("nimmi_user_name") ?? ""); } catch { /* storage blocked */ }
        setInOtherWorkspace(!!getWorkspace());
        apiJson<Workspace[]>("/api/team/workspaces").then(setWorkspaces).catch(() => {});
    }, []);
    useEffect(() => { if (userName) setName(userName); }, [userName]);

    useEffect(() => {
        if (!menu) return;
        const close = (e: MouseEvent | KeyboardEvent) => {
            if (e instanceof KeyboardEvent ? e.key === "Escape" : !menuRef.current?.contains(e.target as Node)) setMenu(false);
        };
        document.addEventListener("mousedown", close);
        document.addEventListener("keydown", close);
        return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
    }, [menu]);

    const current = workspaces.find((w) => w.owner_id === activeOwnerId()) ?? workspaces[0];
    const role = current?.role ?? "owner";
    const initial = name.trim().charAt(0).toUpperCase();

    const switchTo = (w: Workspace) => {
        setWorkspace(w.owner_id);
        window.location.href = "/dashboard"; // reload so every view reads the new workspace
    };

    const signOut = () => {
        clearSession();
        router.push("/auth/login");
    };

    return (
        <header className="bg-white border-b border-line">
            <div className="max-w-6xl mx-auto px-4 sm:px-6 flex flex-wrap items-center gap-x-8">
                <Link href="/dashboard" className="h-14 flex items-center gap-2 shrink-0 rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum">
                    <Image src="/favicon.png" alt="" width={26} height={26} />
                    <span className="text-[15px] font-semibold text-plum tracking-tight">Nimmi AI</span>
                </Link>

                <nav aria-label="Main" className="order-last md:order-none w-full md:w-auto -mb-px flex gap-6 overflow-x-auto [scrollbar-width:none]">
                    {nav.filter((n) => (!n.ownerOnly || role === "owner") && (!n.managerOnly || role !== "agent")).map((item) => {
                        const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                data-agent={`nav.${(item.href.split("/")[2] ?? "assistants").replace("-", "_")}`}
                                aria-current={active ? "page" : undefined}
                                className={cn(
                                    "h-11 md:h-14 inline-flex items-center gap-1.5 text-sm border-b-2 whitespace-nowrap transition-colors",
                                    active ? "border-plum text-ink font-medium" : "border-transparent text-stone-500 hover:text-ink",
                                )}
                            >
                                {item.label}
                                {item.href === "/dashboard/live-chat" && waiting > 0 && (
                                    <span className="min-w-5 h-5 px-1.5 rounded-full bg-signal text-white text-[11px] font-medium tabular-nums inline-flex items-center justify-center">
                                        {waiting}<span className="sr-only"> waiting</span>
                                    </span>
                                )}
                            </Link>
                        );
                    })}
                </nav>

                <AgentToggle className="ml-auto" />

                <div ref={menuRef} className="relative">
                    <button
                        onClick={() => setMenu((m) => !m)}
                        aria-expanded={menu}
                        aria-haspopup="menu"
                        className="flex items-center gap-2 h-9 pl-1 pr-2 rounded-full hover:bg-stone-100 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum"
                    >
                        <span className="h-7 w-7 rounded-full bg-plum-tint text-plum text-[13px] font-semibold flex items-center justify-center">
                            {initial || <span className="h-3 w-3 rounded-full bg-plum/20" />}
                        </span>
                        {inOtherWorkspace && current && <span className="hidden sm:inline text-[13px] text-stone-600 max-w-40 truncate">{current.name}</span>}
                        <ChevronDown size={14} className="text-stone-400" aria-hidden />
                    </button>

                    {menu && (
                        <div role="menu" className="absolute right-0 top-11 z-50 w-64 bg-white border border-line rounded-lg shadow-[0_12px_40px_rgba(28,23,25,0.14)] py-1.5 text-sm">
                            <div className="px-3 py-2 border-b border-line mb-1">
                                <p className="font-medium truncate">{name || "Your account"}</p>
                                {current && <p className="text-xs text-stone-500 truncate">{current.name} · {role === "owner" ? "Owner" : role === "admin" ? "Admin" : "Agent"}</p>}
                            </div>
                            {workspaces.length > 1 && (
                                <div className="border-b border-line pb-1 mb-1">
                                    <p className="px-3 pt-1 pb-1 text-xs text-stone-500">Switch workspace</p>
                                    {workspaces.map((w) => (
                                        <button key={w.owner_id} role="menuitem" onClick={() => switchTo(w)}
                                                className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-stone-50">
                                            <span className="flex-1 truncate">{w.name}</span>
                                            {w.owner_id === current?.owner_id && <Check size={14} className="text-plum" />}
                                        </button>
                                    ))}
                                </div>
                            )}
                            <MenuLink href="/dashboard/profile" onClick={() => setMenu(false)}>Profile</MenuLink>
                            {role === "owner" && <MenuLink href="/dashboard/team" onClick={() => setMenu(false)}>Team</MenuLink>}
                            {role !== "agent" && <MenuLink href="/dashboard/integrations" onClick={() => setMenu(false)}>Integrations</MenuLink>}
                            <button role="menuitem" onClick={signOut} className="w-full text-left px-3 py-1.5 text-stone-600 hover:bg-stone-50 hover:text-ink">
                                Sign out
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </header>
    );
}

function MenuLink({ href, onClick, children }: { href: string; onClick: () => void; children: React.ReactNode }) {
    return (
        <Link role="menuitem" href={href} onClick={onClick} className="block px-3 py-1.5 text-stone-700 hover:bg-stone-50 hover:text-ink">
            {children}
        </Link>
    );
}
