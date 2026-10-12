// Data contract for the Integrations page; mirrors backend/routers/integrations.py.

export type AutomationKey = "chat_lead" | "call_lead";

export interface Automation {
    enabled: boolean;
    delay: "now" | "1h" | "1d";
    subject: string;
    body: string;
}

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
    // WhatsApp two-way AI chat
    whatsapp_chat_enabled: boolean;
    whatsapp_bot_id: string;
    whatsapp_phone_number_id: string;
    whatsapp_has_token: boolean;
    whatsapp_access_token?: string;
    whatsapp_verify_token: string;
    whatsapp_business_account_id: string;
    whatsapp_webhook_url: string;
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
    call_whatsapp: { label: "WhatsApp confirmation", channel: "whatsapp" },
    whatsapp_chat: { label: "WhatsApp chat", channel: "whatsapp" },
    lead_webhook: { label: "Webhook: lead", channel: "webhook" },
    call_webhook: { label: "Webhook: call", channel: "webhook" },
    lead_leadsquared: { label: "LeadSquared: lead", channel: "crm" },
    call_leadsquared: { label: "LeadSquared: call", channel: "crm" },
};

export const AUTOMATIONS: { key: AutomationKey; title: string; trigger: string }[] = [
    { key: "chat_lead", title: "After a chat", trigger: "When someone shares their email with your assistant in chat or on WhatsApp" },
    { key: "call_lead", title: "After a call", trigger: "When a caller gives their email on a call. {{summary}} is the call summary." },
];

export const SAMPLE: Record<string, string> = {
    name: "Priya", business: "", assistant: "Nimmi", email: "priya@example.com", phone: "+91 98765 43210",
    summary: "Priya asked about weekend site visits for a 2BHK and booked Saturday at 11am.",
};

export function renderTemplate(text: string, values: Record<string, string>) {
    return text.replace(/\{\{\s*(\w+)\s*\}\}/g, (_, k: string) => values[k.toLowerCase()] ?? "");
}
