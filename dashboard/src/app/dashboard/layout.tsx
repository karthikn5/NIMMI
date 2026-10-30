import type { Metadata } from "next";
import type { ReactNode } from "react";
import AgentProvider from "@/components/agent/AgentProvider";
import CallDeskProvider from "@/components/voice/CallDesk";

// The signed-in app: never in search results (next.config.ts also sends X-Robots-Tag for it).
export const metadata: Metadata = {
    title: "Dashboard",
    robots: { index: false, follow: false },
};

export default function DashboardLayout({ children }: { children: ReactNode }) {
    return <AgentProvider><CallDeskProvider>{children}</CallDeskProvider></AgentProvider>;
}
