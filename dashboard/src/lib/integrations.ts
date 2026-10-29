// Data contract for the Integrations page; mirrors backend/routers/integrations.py.

export type AutomationKey = "chat_lead" | "handoff_done" | "call_lead" | "goal_met" | "call_missed";

export type Delay = "now" | "1h" | "1d" | "2d" | "3d" | "5d" | "7d" | "14d";

export interface EmailStep {
    delay: Delay;
    subject: string;
    body: string;
}

/** One trigger: the first email, then up to two follow-ups. */
export interface Automation {
    enabled: boolean;
    steps: EmailStep[];
}

export const MAX_STEPS = 3;

/** Seconds after the trigger, matching backend DELAYS. */
export const DELAY_SECONDS: Record<Delay, number> = {
    now: 0, "1h": 3600, "1d": 86400, "2d": 172800, "3d": 259200, "5d": 432000, "7d": 604800, "14d": 1209600,
};

export const DELAY_LABEL: Record<Delay, string> = {
    now: "Right away", "1h": "1 hour later", "1d": "1 day later", "2d": "2 days later", "3d": "3 days later",
    "5d": "5 days later", "7d": "1 week later", "14d": "2 weeks later",
};

export interface IntegrationSettings {
    // Email: team alerts
    email_alerts: boolean;          // new leads
    alert_calls: boolean;           // call summaries
    alert_handoffs: boolean;        // a customer asked for a person
    alert_email: string;            // comma-separated, up to 5
    default_email: string;
    // Email: to customers
    sender_name: string;
    reply_to: string;
    automations: Record<AutomationKey, Automation>;
    placeholders: string[];
    // WhatsApp confirmations after calls
    whatsapp_enabled: boolean;
    whatsapp_template: string;
    whatsapp_language: string;
    // Webhook and CRM
    webhook_url: string;
    webhook_secret: string;
    leadsquared_enabled: boolean;
    leadsquared_host: string;
    leadsquared_access_key: string;
    leadsquared_has_secret: boolean;
    leadsquared_secret_key?: string;
    server: { email: boolean; whatsapp: boolean };
}

export type LogRow = {
    id: string;
    kind: string;
    status: "sent" | "failed" | "skipped" | "sending";
    error: string | null;
    created_at: string | null;
};

export const LOG_KIND: Record<string, { label: string; channel: "email" | "whatsapp" | "webhook" | "crm" }> = {
    lead_email: { label: "Lead alert", channel: "email" },
    call_email: { label: "Call summary", channel: "email" },
    handoff_email: { label: "Person requested", channel: "email" },
    auto_chat_lead: { label: "Customer email after chat", channel: "email" },
    auto_call_lead: { label: "Customer email after call", channel: "email" },
    auto_goal_met: { label: "Customer email, goal met", channel: "email" },
    auto_call_missed: { label: "Customer email, couldn't reach", channel: "email" },
    auto_handoff_done: { label: "Customer email after team chat", channel: "email" },
    call_whatsapp: { label: "WhatsApp confirmation", channel: "whatsapp" },
    whatsapp_chat: { label: "WhatsApp chat", channel: "whatsapp" },
    lead_webhook: { label: "Webhook: lead", channel: "webhook" },
    call_webhook: { label: "Webhook: call", channel: "webhook" },
    lead_leadsquared: { label: "LeadSquared: lead", channel: "crm" },
    call_leadsquared: { label: "LeadSquared: call", channel: "crm" },
};

/** How a log row's kind reads, including follow-ups ("auto_chat_lead#2") and bulk email ("auto_broadcast:<id>"). */
export function logKind(kind: string) {
    if (kind.startsWith("auto_broadcast:")) return { label: "Bulk email", channel: "email" as const };
    const [base, step] = kind.split("#");
    const k = LOG_KIND[base];
    return k && step ? { ...k, label: `${k.label}, follow-up ${Number(step) - 1}` } : k;
}

export const AUTOMATIONS: { key: AutomationKey; group: "Chat" | "Calls"; title: string; trigger: string }[] = [
    { key: "chat_lead", group: "Chat", title: "After a chat", trigger: "When someone shares their email with your assistant in chat or on WhatsApp." },
    { key: "handoff_done", group: "Chat", title: "After your team helps", trigger: "When someone from your team closes a Live chat with a customer who shared their email." },
    { key: "call_lead", group: "Calls", title: "After a call", trigger: "When a caller gives their email on a call. {{summary}} is the call summary." },
    { key: "goal_met", group: "Calls", title: "Goal met on a call", trigger: "When a call reaches the agent's goal, like a booking. Sent instead of \"After a call\". {{details}} lists what was collected." },
    { key: "call_missed", group: "Calls", title: "Couldn't reach them", trigger: "When a call-back or campaign call goes unanswered after the last retry, and we have their email." },
];

export const SAMPLE: Record<string, string> = {
    name: "Priya", business: "", assistant: "Nimmi", email: "priya@example.com", phone: "+91 98765 43210",
    summary: "Priya asked about weekend site visits for a 2BHK and booked Saturday at 11am.",
    details: "Visit date: Saturday, 11 AM\nBudget: 60-70 lakh",
};

/* ---------- Email history and bulk email (backend/routers/email_center.py) ---------- */

export type EmailStatus = "queued" | "sent" | "failed" | "cancelled";

export interface EmailRow {
    id: string;
    to: string;
    subject: string;
    automation: AutomationKey | "broadcast";
    label: string;
    step: number;
    status: EmailStatus;
    error: string | null;
    broadcast_id: string | null;
    send_at: string | null;
    sent_at: string | null;
    created_at: string | null;
}

export interface EmailHistory {
    items: EmailRow[];
    counts: Record<EmailStatus, number>;
    total: number;
}

export type AudienceSource = "all" | "chat" | "calls";

export interface Audience {
    count: number;
    sample: { name: string; email: string; source: "chat" | "call"; last_seen: string | null }[];
    unsubscribed: number;
    limit: number;
}

export interface Broadcast {
    id: string;
    subject: string;
    audience: { source?: AudienceSource; days?: number; hot_only?: boolean };
    recipients: number;
    created_at: string | null;
    counts: Record<EmailStatus, number>;
}

export function renderTemplate(text: string, values: Record<string, string>) {
    return text.replace(/\{\{\s*(\w+)\s*\}\}/g, (_, k: string) => values[k.toLowerCase()] ?? "");
}
