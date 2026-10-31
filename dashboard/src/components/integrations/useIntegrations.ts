"use client";

import { useState } from "react";
import { useToast } from "@/components/ui";
import { apiJson } from "@/lib/api";
import type { IntegrationSettings } from "@/lib/integrations";
import { useApi, useDraft } from "@/lib/useApi";
import type { PanelProps, TestChannel } from "./shared";

/** The workspace's integration settings (backend routers/integrations.py), edited as a draft and saved together. Used
 * by the Integrations page and the Email section's Automations and Bulk email pages. */
export function useIntegrations(onTested?: () => void) {
    const toast = useToast();
    const settings = useApi<IntegrationSettings>("/api/integrations");
    const { draft, setDraft, dirty, saving, save, discard } = useDraft(settings, "/api/integrations");
    const [testing, setTesting] = useState<string | null>(null);

    const test: PanelProps["test"] = async (channel: TestChannel, automation?: string, phone?: string) => {
        if (dirty) return toast("Save your changes first, so the test uses them.");
        const key = automation ? `${channel}:${automation}` : channel;
        setTesting(key);
        try {
            await apiJson("/api/integrations/test", { method: "POST", json: { channel, automation, to_phone: phone } });
            toast(channel === "whatsapp" ? "Test message sent" : channel === "email_automation" ? "Test email sent to your alert address" : "Test sent");
        } catch (e) {
            toast((e as Error).message);
        } finally {
            setTesting(null);
            onTested?.();
        }
    };

    const props: PanelProps | null = draft
        ? { draft, saved: settings.data, set: (k, v) => setDraft({ ...draft, [k]: v }), test, testing }
        : null;
    return { settings, draft, dirty, saving, save, discard, props };
}
