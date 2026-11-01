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
export type EmailKind = "welcome" | "after_call" | "meeting" | "lead_email" | "callback_booked" | "voicemail" | "missed_chat" | "chat_copy" | "during_call";
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
        replies: { mode: ReplyMode };
        during_call: { enabled: boolean };
        lead_email: { enabled: boolean }; lead_call: { enabled: boolean; minutes: number };
        callback_booked: { enabled: boolean }; voicemail: { enabled: boolean }; missed_chat: { enabled: boolean; minutes: number };
        chat_copy: { enabled: boolean }; meeting: { thanks: boolean; missed: boolean };
    };
    kinds: { kind: EmailKind; label: string; about: string; placeholders: string[]; languages: Language[]; saved: Language[] }[];
    languages: Record<Language, string>;
    delays: string[];
    replies_on: boolean;  // REPLY_DOMAIN is set on the server: replies come back to Nimmi
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

/* Leads from other places (backend mail/intake.py, mail/leads_api.py). */
export interface LeadSources {
    bot_id: string;
    bot_name: string;
    enabled: boolean;
    receiving: boolean;           // emails can be forwarded in: REPLY_DOMAIN is set
    address: string | null;
    indiamart_url: string | null;
    form_url: string | null;
    forwarding: { code: string | null; link: string | null; at: string } | null;  // Gmail's confirmation
    lead_email: { enabled: boolean };
    lead_call: { enabled: boolean; minutes: number };
    recent: { id: string; channel: string; source: string | null; status: string; note: string | null; subject: string | null;
              found: { name?: string; phone?: string; email?: string; wants?: string }; created_at: string | null }[];
}

/* Conversations by email (backend mail/inbox.py, mail/replies.py). */
export type ReplyMode = "ai" | "draft" | "team";
export type ThreadStatus = "open" | "answered" | "closed";
export type ReplyKind = "question" | "call_me" | "meeting" | "not_interested" | "stop" | "thanks" | "auto_reply" | "other";

export interface ThreadRow {
    id: string;
    email: string;
    name: string | null;
    subject: string | null;
    status: ThreadStatus | "quiet";
    kind: ReplyKind | null;
    unread: number;
    assigned_to: string | null;
    bot_id: string | null;
    bot_name: string | null;
    last_at: string | null;
    last: string | null;   // their latest words
    draft: boolean;        // the AI's answer is waiting
}

export interface Threads { items: ThreadRow[]; counts: Record<ThreadStatus, number>; unread: number; enabled: boolean }

export interface ThreadMessageRow {
    id: string;
    direction: "in" | "out";
    who: "customer" | "team" | "ai" | "nimmi";
    status: string;
    subject: string | null;
    text: string | null;
    kind: ReplyKind | null;
    note: string | null;
    sender: string | null;
    attachments: { id: string; filename: string; content_type: string; size: number | null }[];
    automatic: boolean;
    by: string | null;
    action: { type: "callback" | "meeting"; at?: string; date?: string; time?: string } | null;
    created_at: string | null;
}

export interface Thread extends ThreadRow {
    notes: string;
    messages: ThreadMessageRow[];
    contact: { name: string | null; phone: string | null; lead_status: string | null; details: Record<string, string> } | null;
    calls: { id: string; at: string | null; summary: string | null; direction: string }[];
    mode: ReplyMode;
}

export const KIND_LABEL: Record<ReplyKind, string> = {
    question: "Question", call_me: "Wants a call", meeting: "Wants to meet", not_interested: "Not interested", stop: "Asked to stop",
    thanks: "Thanks", auto_reply: "Automatic message", other: "Other",
};

export const REPLY_MODES: { value: ReplyMode; label: string }[] = [
    { value: "draft", label: "AI writes, your team sends" }, { value: "ai", label: "AI answers" }, { value: "team", label: "Your team only" },
];

/* Journeys and lead stages (backend mail/journeys.py, mail/journeys_api.py). */
export type JourneyStep =
    | { type: "email"; subject: string; body: string; ai?: boolean }
    | { type: "wait"; days?: number; hours?: number; weekday?: string; at?: string; until?: string }
    | { type: "whatsapp"; text: string; subject?: string; template?: string }
    | { type: "call"; about: string }
    | { type: "branch"; if: string; not?: boolean; then: "end" | "skip"; skip?: number }
    | { type: "update"; stage?: string; status?: string; tag?: string; owner?: string }
    | { type: "notify"; text: string; todo?: boolean };
export type JourneyStepKind = JourneyStep["type"];

export interface Journey {
    id: string;
    bot_id: string;
    name: string;
    trigger: string;
    trigger_value: string | null;
    goal: string | null;
    steps: JourneyStep[];
    options: { days_before?: number; yearly?: boolean };
    enabled: boolean;
    counts: { active?: number; done?: number; stopped?: number };
    updated_at: string | null;
}

export interface TeamPerson { id: string; name: string }

export interface Journeys {
    items: Journey[];
    ready: { key: string; name: string; about: string }[];
    triggers: Record<string, string>;
    sources: Record<string, string>;
    goals: Record<string, string>;
    tests: Record<string, string>;
    statuses: Record<string, string>;
    stages: string[];
    days: string[];
    details: string[];
    team: TeamPerson[];
    cap: { per_day: number; per_week: number };
    already_running: { name: string; on: boolean; where: string }[];
}

export interface JourneyRunRow {
    id: string;
    name: string | null;
    email: string | null;
    status: "active" | "done" | "stopped";
    step: number;
    next_at: string | null;
    reason: string | null;
    history: { step: number; at: string; what: string }[];
    started_at: string | null;
}

export interface Lead {
    id: string;
    name: string | null;
    email: string | null;
    phone: string | null;
    stage: string;
    status: string | null;
    assigned_to: string | null;
    tags: string[];
    source: string | null;
    last_at: string | null;
    agreed: boolean;              // to offers and news
}

export interface Board { stages: string[]; team: TeamPerson[]; total: number; leads: Lead[] }

export const STAGE_LABEL: Record<string, string> = {
    new: "New", contacted: "Contacted", interested: "Interested", meeting: "Meeting", customer: "Customer", lost: "Lost",
};

/* Who asked a question, for the team to tick (backend mail/answers.py). */
export interface AskedBy {
    people: { id: string; email: string; name: string | null; channel: string | null; asked_at: string | null; sent: boolean }[];
    without_email: number;
}

/* Bulk email (backend mail/broadcasts.py, mail/broadcasts_api.py). Only people who agreed to offers and news get it. */
export type BulkStatus = "draft" | "scheduled" | "testing" | "sending" | "paused" | "sent" | "cancelled";

export interface BulkRules {
    statuses?: string[];
    stages?: string[];
    sources?: string[];
    tags?: string[];
    active_days?: number;
    engaged_days?: number;
}

export interface BulkEvent { title: string; at: string; where?: string }

export interface BulkCounts {
    queued: number; held: number; sent: number; failed: number; cancelled: number;
    delivered: number; bounced: number; complained: number; clicked: number; replied: number; unsubscribed: number;
}

export interface BulkVariant { sent: number; clicked: number; replied: number }

export interface BulkEmail {
    id: string;
    bot_id: string | null;        // none: sent before November 2026, from the whole workspace
    status: BulkStatus;
    subject: string;
    subject_b: string | null;     // a second subject to test on part of the list
    body: string;
    rules: BulkRules;
    event: BulkEvent | null;      // an invitation
    recipients: number;
    winner: "a" | "b" | null;
    send_at: string | null;
    usual_hour: boolean;
    per_minute: number;
    test_ends_at: string | null;
    started_at: string | null;
    finished_at: string | null;
    paused_why: string | null;
    created_at: string | null;
    counts?: BulkCounts;
    variants?: { a: BulkVariant; b: BulkVariant } | null;
    rsvp?: { yes: number; no: number; maybe: number } | null;
    notes?: string[];             // common reasons for landing in spam
    no_mail_server?: number;      // left out when it started: their domain takes no mail
}

export interface BulkGroup { id: string; name: string; rules: BulkRules }

export interface BulkPage {
    broadcasts: BulkEmail[];
    segments: BulkGroup[];
    agreed: number;
    with_email: number;
    ask_in_chat: { ask: boolean; words: string };
    sender: { name: string; address: string; domain: string | null; reply_to: string | null };
    room_today: number | null;    // none: no daily limit
    max_recipients: number;
    paces: number[];
    test_min: number;
    tags: string[];
    sources: Record<string, string>;
    statuses: Record<string, string>;
    stages: string[];
    spam_rate: number | null;
}

export interface BulkCount {
    count: number;
    left_out: { no_consent: number; stopped: number; throwaway: number };
    sample: { name: string; email: string }[];
}

export interface ImportResult {
    rows: number; added: number; updated: number; agreed: number;
    skipped: { line: number; why: string }[]; skipped_count: number;
}

export const BULK_STATUS: Record<BulkStatus, { label: string; tone: "good" | "neutral" | "warn" | "bad" }> = {
    draft: { label: "Draft", tone: "neutral" }, scheduled: { label: "Scheduled", tone: "neutral" }, testing: { label: "Testing subjects", tone: "good" },
    sending: { label: "Going out", tone: "good" }, paused: { label: "Paused", tone: "warn" }, sent: { label: "Sent", tone: "good" }, cancelled: { label: "Cancelled", tone: "neutral" },
};

