"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiJson } from "@/lib/api";
import { Notice } from "@/components/ui";

/** The workspace's plan limits (see backend/plans.py). */
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
    used: { assistants: number; sites: number };
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

/** A quiet note at the top of a paid-only screen, with the way to upgrade. */
export function PaidOnly({ feature, children }: { feature: string; children?: React.ReactNode }) {
    return (
        <Notice title={`${feature} come with a paid plan`}
                action={<Link href="/dashboard/billing" className="inline-flex items-center h-8 px-3 rounded-md bg-plum text-white text-[13px] font-medium hover:bg-plum-hover">Choose a plan</Link>}>
            {children ?? "Choose a plan for one of your assistants to turn them on. Everything else keeps working on the free plan."}
        </Notice>
    );
}
