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
    host: string;      // relative to the domain's zone ("send", "resend._domainkey", "send.mail"); "@" for the domain itself
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

/* An assistant's emails and their designs (backend mail/api.py setup and designs; mail/designs.py). */
export type EmailKind = "welcome" | "after_call" | "meeting" | "callback_booked" | "voicemail" | "missed_chat" | "chat_copy" | "during_call";
export type Language = "en" | "ta" | "hi";
export type ButtonAction = "book" | "call" | "whatsapp" | "link" | "join" | "change" | "cancel";

export type Block =
    | { type: "text"; text: string }
    | { type: "heading"; text: string }
    | { type: "ai_note"; guidance?: string }
    | { type: "call_summary" }
    | { type: "meeting" }
    | { type: "files" }
    | { type: "button"; label: string; action: ButtonAction; url?: string }
    | { type: "details" }
    | { type: "transcript" }
    | { type: "signature" }
    | { type: "divider" }
    | { type: "image"; url: string; alt?: string };

export interface Design { subject: string; blocks: Block[]; language: Language; saved: boolean }

export interface EmailStepIn { delay: string; subject: string; body: string }
export interface AutomationIn { enabled: boolean; steps: EmailStepIn[] }

export interface AssistantEmails {
    bot_id: string;
    bot_name: string;
    automations: Record<string, AutomationIn>;
    own_automations: boolean;
    settings: {
        welcome: { ai_note: boolean; files: string[]; ai_files: boolean; max_files: number };
        after_call: { inbound: AfterCallMode; outbound: AfterCallMode; approved: number; approved_unchanged: number; suggested: boolean };
        callback_booked: { enabled: boolean }; voicemail: { enabled: boolean }; missed_chat: { enabled: boolean; minutes: number };
        chat_copy: { enabled: boolean }; meeting: { thanks: boolean; missed: boolean };
    };
    kinds: { kind: EmailKind; label: string; about: string; placeholders: string[]; languages: Language[]; saved: Language[] }[];
    languages: Record<Language, string>;
    delays: string[];
}

export interface Preview { subject: string; html: string; text: string; preheader: string; from: string; reply_to: string | null; too_big: boolean }

/* The AI's after-call emails waiting for the team (backend mail/api.py drafts; mail/after_call.py). */
export type AfterCallMode = "off" | "review" | "auto";

export interface DraftAnswer { q: string; a: string }

export interface Draft {
    id: string;
    to: string;
    name: string | null;
    phone: string | null;
    bot_id: string;
    bot_name: string | null;
    direction: "inbound" | "outbound";
    call_id: string;
    language: string;
    created_at: string | null;
    subject: string;              // the team's own; empty uses the design's
    state: "writing" | "ready" | "failed";
    note: string | null;          // why it waits for a person, when something held it
    fixed: string | null;         // what the AI's check corrected
    unanswered: string[];         // questions that went to Questions
    recap: string[];
    answers: DraftAnswer[];
    next_step: string;
    file_ids: string[];
}

export interface DraftDetail extends Draft {
    html: string;
    text: string;
    shown_subject: string;
    from: string;
    reply_to: string | null;
    files_available: { id: string; name: string; size: string }[];
}

export interface Drafts {
    items: Draft[];
    total: number;
    suggest: { bot_id: string; bot_name: string; approved: number; unchanged: number }[];
}

/** After a draft is sent or discarded: the tab's count follows. */
export const DRAFTS_CHANGED = "nimmi:email-drafts";

export const BLOCK_LABEL: Record<Block["type"], string> = {
    text: "Text", heading: "Heading", ai_note: "The AI's note", call_summary: "The call's summary", meeting: "Meeting details",
    files: "Files", button: "Button", details: "What they told us", transcript: "The chat", signature: "Signature",
    divider: "Divider", image: "Image",
};

export const ACTION_LABEL: Record<ButtonAction, string> = {
    book: "Book a time", call: "Call me back", whatsapp: "Chat on WhatsApp", link: "Open a link", join: "Join the meeting",
    change: "Change the meeting's time", cancel: "Cancel the meeting",
};
