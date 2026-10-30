"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiJson } from "@/lib/api";
import { Notice } from "@/components/ui";

/** What a plan includes (backend plans.py `Includes`; "earlier": a 1/6/12 Month plan, everything until it ends). */
export type Includes = {
    tier: "starter" | "growth" | "pro" | "earlier" | null; replies: number | null; seats: number; call_credits: number;
    whatsapp: boolean; live_chat: boolean; email_alerts: boolean; schedule: boolean; campaigns: boolean; integrations: boolean;
    business_hours: boolean; transfers: boolean;
};
export type Feature = "whatsapp" | "live_chat" | "email_alerts" | "schedule" | "campaigns" | "integrations" | "business_hours" | "transfers";

/** The workspace's plan limits (see backend/plans.py): `includes` is its best plan (for what assistants share), and
 * `assistant_plans` each assistant's, with its AI replies this month. */
export type Limits = {
    paid: boolean;
    assistants: number | null;
    sites: number;
    custom_domains: boolean;
    voice: boolean;
    integrations: boolean;
    deploy_bytes: number;
    deploy_files: number;
    file_bytes: number;
    deploys_kept: number;
    used: { assistants: number; sites: number; seats?: number };
    includes?: Includes;
    assistant_plans?: Record<string, Includes & { name: string; replies_used: number }>;
};

/** What each feature is called, and the plan it starts on (the backend's NEEDS). */
export const NEEDS: Record<Feature, { text: string; tier: "Growth" | "Pro" }> = {
    whatsapp: { text: "WhatsApp comes", tier: "Growth" },
    live_chat: { text: "Live chat comes", tier: "Growth" },
    email_alerts: { text: "Email alerts and follow-ups come", tier: "Growth" },
    schedule: { text: "Call-backs and follow-up calls come", tier: "Pro" },
    campaigns: { text: "Campaigns come", tier: "Pro" },
    integrations: { text: "Webhooks, LeadSquared and Google Sheets come", tier: "Pro" },
    business_hours: { text: "Business hours come", tier: "Pro" },
    transfers: { text: "Transfers to your team come", tier: "Pro" },
};

export function useLimits() {
    const [limits, setLimits] = useState<Limits | null>(null);
    useEffect(() => {
        apiJson<Limits>("/api/account/limits").then(setLimits).catch(() => { /* the server enforces limits anyway */ });
    }, []);
    return limits;
}

export const formatBytes = (n: number) =>
    n >= 1024 * 1024 ? `${(n / (1024 * 1024)).toFixed(n >= 10 * 1024 * 1024 ? 0 : 1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`;

/** A quiet note where something needs a plan the assistant (or, for what they share, the workspace) isn't on. */
export function PlanNeeded({ feature, botId, className, children }: { feature: Feature; botId?: string; className?: string; children?: React.ReactNode }) {
    const { text, tier } = NEEDS[feature];
    return (
        <Notice title={`${text} with the ${tier} plan`} className={className}
                action={<Link href={botId ? `/dashboard/billing?bot=${botId}` : "/dashboard/billing"}
                              className="inline-flex items-center h-8 px-3 rounded-md bg-plum text-white text-[13px] font-medium hover:bg-plum-hover">Choose a plan</Link>}>
            {children ?? `Choose ${tier} for ${botId ? "this assistant" : "one of your assistants"} on the Billing page to turn it on.`}
        </Notice>
    );
}

/** A quiet note at the top of a paid-only screen, with the way to upgrade. */
export function PaidOnly({ feature, children }: { feature: string; children?: React.ReactNode }) {
    return (
        <Notice title={`${feature} come with a paid plan`}
                action={<Link href="/dashboard/billing" className="inline-flex items-center h-8 px-3 rounded-md bg-plum text-white text-[13px] font-medium hover:bg-plum-hover">Choose a plan</Link>}>
            {children ?? "Choose a plan for one of your assistants to turn them on. Everything else keeps working on the free plan."}
        </Notice>
    );
}
