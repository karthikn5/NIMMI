/* The Email section (backend mail/api.py). History, bulk email and automations use lib/integrations.ts. */
import type { AutomationKey, EmailRow } from "@/lib/integrations";

export interface EmailOverview {
    server: { email: boolean; resend: boolean; events: boolean; sending_address: string };
    last_30_days: Record<"queued" | "sent" | "failed" | "cancelled" | "delivered" | "bounced" | "complained" | "opened" | "clicked", number>;
    automations: { key: AutomationKey; label: string; enabled: boolean; emails: number }[];
    domains: { id: string; name: string; status: string; status_label: string }[];
    stopped: number;
    complaint_rate: number | null;
    problems: EmailRow[];
}

export interface DnsRecord {
    purpose: string;   // DKIM, SPF, MX...
    type: string;      // TXT, MX, CNAME
    host: string;      // relative to the domain ("send", "resend._domainkey"); "@" for the domain itself
    full_name: string;
    value: string;
    priority: number | null;
    status: string;
}

export interface SendingDomain {
    id: string;
    name: string;
    status: string;
    status_label: string;
    verified: boolean;
    records: DnsRecord[];
    own_key: boolean;
    bulk_today: number | null;  // bulk emails it may send today while it warms up; null = no limit
    created_at: string | null;
    checked_at: string | null;
    verified_at: string | null;
}

export interface SendsAs { name: string; address: string; reply_to: string | null; domain: string | null }

export interface SenderFields { from_name: string; local_part: string; domain_id: string; reply_to: string }

export interface Senders {
    default: SenderFields & { sends_as: SendsAs };
    assistants: (SenderFields & { bot_id: string; bot_name: string; sends_as: SendsAs })[];
    domains: { id: string; name: string; verified: boolean }[];
    nimmi_address: string;
}

export type StopReason = "unsubscribed" | "complaint" | "bounce" | "team";

export interface Suppressions {
    items: { id: string; email: string; reason: StopReason; text: string; only_marketing: boolean; bot_name: string | null;
             created_at: string | null; removable: boolean }[];
    counts: Partial<Record<StopReason, number>>;
    total: number;
}
