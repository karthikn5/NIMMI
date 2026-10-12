"use client";

import { Suspense, useEffect, useState, type ComponentType } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Activity, Contact, Mail, MessageCircle, Webhook } from "lucide-react";
import AppHeader from "@/components/AppHeader";
import { SaveBar, Skeleton, Status, ToastProvider, cn, useToast } from "@/components/ui";
import { EmailPanel } from "@/components/integrations/EmailPanel";
import { ActivityPanel, LeadSquaredPanel, WebhookPanel } from "@/components/integrations/OtherPanels";
import { WhatsAppPanel } from "@/components/integrations/WhatsAppPanel";
import type { PanelProps, TestChannel } from "@/components/integrations/shared";
import { apiJson, currentUserId } from "@/lib/api";
import type { IntegrationSettings, LogRow } from "@/lib/integrations";
import { useApi, useDraft } from "@/lib/useApi";

type Tab = "email" | "whatsapp" | "webhook" | "leadsquared" | "activity";
type Tone = "good" | "neutral" | "warn" | "bad";

const TABS: { id: Tab; label: string; hint: string; icon: ComponentType<{ size?: number; className?: string }> }[] = [
    { id: "email", label: "Email", hint: "Alerts and customer follow-ups", icon: Mail },
    { id: "whatsapp", label: "WhatsApp", hint: "AI chat and confirmations", icon: MessageCircle },
    { id: "webhook", label: "Webhook", hint: "Your own system, Zapier, Make", icon: Webhook },
    { id: "leadsquared", label: "LeadSquared", hint: "CRM sync", icon: Contact },
    { id: "activity", label: "Activity", hint: "What went out", icon: Activity },
];

function status(tab: Tab, s: IntegrationSettings, log: LogRow[] | null): { label: string; tone: Tone } {
    switch (tab) {
        case "email": {
            const on = s.email_alerts || s.alert_calls || s.alert_handoffs || Object.values(s.automations).some((a) => a.enabled);
            if (on && !s.server.email) return { label: "Needs setup", tone: "warn" };
            return on ? { label: "On", tone: "good" } : { label: "Off", tone: "neutral" };
        }
        case "whatsapp":
            return s.whatsapp_chat_enabled && s.whatsapp_has_token && s.whatsapp_phone_number_id
                ? { label: "Connected", tone: "good" } : { label: "Not connected", tone: "neutral" };
        case "webhook":
            return s.webhook_url ? { label: "On", tone: "good" } : { label: "Off", tone: "neutral" };
        case "leadsquared":
            return s.leadsquared_enabled ? { label: "On", tone: "good" } : { label: "Off", tone: "neutral" };
        case "activity": {
            const failed = (log ?? []).filter((r) => r.status === "failed").length;
            return failed ? { label: `${failed} failed`, tone: "bad" } : { label: "All clear", tone: "neutral" };
        }
    }
}

export default function IntegrationsPage() {
    return (
        <ToastProvider>
            <div className="min-h-screen bg-paper text-ink">
                <AppHeader />
                <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 pb-28">
                    <h1 className="text-2xl font-semibold tracking-tight">Integrations</h1>
                    <p className="text-sm text-stone-500 mt-1">Where leads, calls and conversations go after your assistants handle them.</p>
                    <Suspense fallback={<Skeleton className="h-96 mt-8" />}>
                        <Integrations />
                    </Suspense>
                </main>
            </div>
        </ToastProvider>
    );
}

function Integrations() {
    const router = useRouter();
    const pathname = usePathname();
    const params = useSearchParams();
    const toast = useToast();
    const settings = useApi<IntegrationSettings>("/api/integrations");
    const log = useApi<LogRow[]>("/api/integrations/log");
    const { draft, setDraft, dirty, saving, save, discard } = useDraft(settings, "/api/integrations");
    const [testing, setTesting] = useState<string | null>(null);
    const requested = params.get("tab") as Tab | null;
    const tab: Tab = TABS.some((t) => t.id === requested) ? requested! : "email";

    useEffect(() => { if (!currentUserId()) router.push("/auth/login"); }, [router]);

    const go = (t: Tab) => router.replace(`${pathname}?tab=${t}`, { scroll: false });

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
            log.reload();
        }
    };

    if (settings.error) return <p className="mt-8 text-sm text-signal">{settings.error}</p>;
    if (!draft) return <Skeleton className="h-96 mt-8" />;
    const set: PanelProps["set"] = (k, v) => setDraft({ ...draft, [k]: v });
    const props: PanelProps = { draft, saved: settings.data, set, test, testing };

    return (
        <div className="mt-8 grid lg:grid-cols-[15rem_minmax(0,1fr)] gap-6 lg:gap-8 items-start">
            {/* The list of integrations stays in view; the chosen one opens beside it. */}
            <nav aria-label="Integrations" className="lg:sticky lg:top-6 -mx-4 px-4 lg:mx-0 lg:px-0 overflow-x-auto [scrollbar-width:none]">
                <ul className="flex lg:flex-col gap-1 min-w-max lg:min-w-0">
                    {TABS.map((t) => {
                        const st = status(t.id, settings.data ?? draft, log.data);
                        const active = t.id === tab;
                        const Icon = t.icon;
                        return (
                            <li key={t.id}>
                                <button
                                    type="button"
                                    onClick={() => go(t.id)}
                                    aria-current={active ? "page" : undefined}
                                    className={cn(
                                        "w-full flex items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors focus-visible:outline-2 focus-visible:outline-plum",
                                        active ? "bg-white border border-line shadow-[0_1px_2px_rgba(28,23,25,0.06)]" : "border border-transparent hover:bg-white/60",
                                    )}
                                >
                                    <Icon size={16} className={cn("shrink-0 lg:self-start lg:mt-0.5", active ? "text-plum" : "text-stone-400")} />
                                    <span className="min-w-0 flex-1">
                                        <span className="flex items-center justify-between gap-2">
                                            <span className={cn("text-sm", active && "font-medium")}>{t.label}</span>
                                            <span className="hidden lg:inline-flex [&>span]:text-xs"><Status tone={st.tone}>{st.label}</Status></span>
                                        </span>
                                        <span className="hidden lg:block text-xs text-stone-500 mt-0.5">{t.hint}</span>
                                    </span>
                                </button>
                            </li>
                        );
                    })}
                </ul>
            </nav>

            <section className="min-w-0">
                {tab === "email" && <EmailPanel {...props} />}
                {tab === "whatsapp" && <WhatsAppPanel {...props} />}
                {tab === "webhook" && <WebhookPanel {...props} />}
                {tab === "leadsquared" && <LeadSquaredPanel {...props} />}
                {tab === "activity" && <ActivityPanel log={log.data} onRefresh={log.reload} />}
            </section>

            <SaveBar visible={dirty} saving={saving} onDiscard={discard} onSave={async () => { toast(await save()); log.reload(); }} />
        </div>
    );
}
