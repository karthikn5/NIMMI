import type { ReactNode } from "react";
import type { IntegrationSettings } from "@/lib/integrations";

export type TestChannel = "email" | "email_automation" | "webhook" | "leadsquared" | "whatsapp";

export interface PanelProps {
    draft: IntegrationSettings;
    saved: IntegrationSettings | null;
    set: <K extends keyof IntegrationSettings>(key: K, value: IntegrationSettings[K]) => void;
    /** Sends a test through the saved settings. `testing` is "<channel>" or "<channel>:<automation>". */
    test: (channel: TestChannel, automation?: string, phone?: string) => void;
    testing: string | null;
}

export function PanelHeader({ title, description, action }: { title: string; description: ReactNode; action?: ReactNode }) {
    return (
        <div className="flex flex-wrap items-start justify-between gap-3 mb-5">
            <div>
                <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
                <p className="text-[13px] text-stone-500 mt-0.5 max-w-2xl">{description}</p>
            </div>
            {action}
        </div>
    );
}
