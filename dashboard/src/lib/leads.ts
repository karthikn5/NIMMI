/** The Leads section (backend/leads). */
import { parseUtc } from "@/lib/voice/api";

export type Stage = "new" | "contacted" | "interested" | "meeting" | "customer" | "lost";

export const STAGES: Record<string, string> = { new: "New", contacted: "Contacted", interested: "Interested", meeting: "Meeting", customer: "Customer", lost: "Lost" };
export const SOURCE: Record<string, string> = { chat: "Website chat", whatsapp: "WhatsApp", instagram: "Instagram", call: "Phone call", manual: "Added by the team", lead: "Lead source" };
export const KIND: Record<string, string> = { call: "Call", whatsapp: "WhatsApp", email: "Email", visit: "Visit", other: "Other" };

/** Where a lead came from, in the order it reads best (backend leads/origin.py). Shown as text, never as links: all of it comes from strangers. */
export const ORIGIN: [string, string][] = [
    ["channel", "Came through"], ["rule", "Comment rule"], ["headline", "Ad headline"], ["ad_text", "Ad text"], ["ad_url", "Ad address"], ["campaign_name", "Campaign"], ["utm_campaign", "Campaign"], ["adset_name", "Ad set"], ["ad_name", "Ad"],
    ["utm_content", "Ad"], ["form_name", "Form"], ["utm_source", "Source"], ["utm_medium", "Medium"], ["utm_term", "Search words"], ["platform", "Platform"], ["landing_page", "Landing page"], ["referrer", "Came from"],
    ["campaign_id", "Campaign id"], ["adset_id", "Ad set id"], ["ad_id", "Ad id"], ["form_id", "Form id"], ["gclid", "Google click id"], ["gbraid", "Google click id"], ["wbraid", "Google click id"], ["fbclid", "Facebook click id"], ["ctwa_clid", "WhatsApp click id"], ["ref", "Link or ad reference"],
];
export const CHANNEL: Record<string, string> = { google_ads: "Google ads", meta_ads: "Facebook or Instagram ads", whatsapp_ad: "A WhatsApp ad", instagram_ad: "An Instagram ad",
    instagram_link: "An Instagram link (ig.me)", instagram_comment: "An Instagram comment", website: "Your website", import: "An imported list" };

export function sourceLabel(source: string | null | undefined) {
    return (source && SOURCE[source]) || source || "Phone call";
}

export interface LeadTask {
    id: string;
    title: string;
    kind: string;
    due_at: string;
    assigned_to: string | null;
    owner?: string | null;
    status: "open" | "done" | "cancelled";
    result: string | null;
    origin: string;
    done_at: string | null;
}

export interface LeadRow {
    id: string;
    name: string | null;
    email: string | null;
    phone: string | null;
    e164: string | null;
    stage: string;
    status: string | null;
    assigned_to: string | null;
    owner: string | null;
    source: string | null;
    origin: Record<string, string> | null;
    tags: string[];
    bot_id: string;
    bot_name: string | null;
    quality: string | null;
    created_at: string | null;
    last_enquiry_at: string | null;
    next: LeadTask | null;
}

export interface Person { id: string; name: string }

export interface Queues {
    overdue: LeadRow[];
    today: LeadRow[];
    new: LeadRow[];
    no_next: LeadRow[];
    asked_for_person: { id: string; name: string | null; phone: string; bot_name: string | null; about: string | null; at: string | null }[];
    meetings: { id: string; name: string | null; phone: string; bot_id: string; bot_name: string | null; about: string | null; starts_at: string | null }[];
    promises?: (LeadPromise & { lead: LeadRow })[];  // phase 7: missing while an older backend answers
}

export type PromiseKind = "send" | "price" | "callback" | "visit" | "other";

/** What the business promised a person (backend leads/promises.py): open until a record shows it was done. */
export interface LeadPromise {
    id: string;
    contact_id: string;
    kind: PromiseKind;
    what: string;
    words: string | null;          // the business's own words, when the AI found it
    made_at: string;
    made_on: "call" | "chat" | "whatsapp" | "instagram" | "email" | "team";
    made_by: string | null;
    due_at: string;
    due_said: boolean;             // a time was said; else it's expected a day after
    status: "open" | "done" | "cancelled";
    late: boolean;
    done_at: string | null;
    done_by: string | null;        // null with evidence: found in the records
    evidence: { kind: string; id: string | null; at: string | null; text: string } | null;
    cancelled_why: string | null;
}

/** A record since the promise that a person can choose as what kept it. */
export interface PromiseEvidence { kind: string; id: string; at: string | null; text: string }

export const PROMISE_KIND: Record<PromiseKind, string> = { send: "Send something", price: "Share a price", callback: "Call them back", visit: "Arrange a visit or meeting", other: "Something else" };
export const MADE_ON: Record<string, string> = { call: "on a phone call", chat: "in the website chat", whatsapp: "on WhatsApp", instagram: "on Instagram", email: "by email", team: "by the team" };

export interface LeadList {
    items: LeadRow[];
    total: number;
    stages: string[];
    sources: string[];
    team: Person[];
    bots: { id: string; name: string }[];
    lost_reasons: string[];
    junk: number;
}

export interface TimelineItem {
    kind: string;
    at: string;
    text: string;
    who?: string | null;
    call_id?: string;
    direction?: string;
    outcome?: string;
    meeting_id?: string;
    starts_at?: string;
    thread_id?: string;
    automation?: string;
    chat_link?: string;
    found?: Record<string, string>;
    origin?: Record<string, string> | null;
    consents?: { id?: string; text?: string; agreed?: boolean }[] | null;
    test?: boolean;
}

export interface Deal {
    id: string;
    outcome: "won" | "lost";
    amount: number | null;
    currency: string;
    reason: string | null;
    source: string | null;
    closed_at: string | null;
    by: string | null;
    reopened: boolean;  // kept on record; not counted in reports
}

export interface LeadDetail extends LeadRow {
    notes: string;
    details: Record<string, unknown>;
    brief: { wants?: string; told?: string; next?: string } | null;
    lead_reason: string | null;
    tasks: LeadTask[];
    deals: Deal[];
    timeline: TimelineItem[];
    enquiry_days_left: number | null;
    team: Person[];
    stages: string[];
    lost_reasons: string[];
    results: Record<string, string>;
    kinds: string[];
    can_assign: boolean;
    junk_reason: string | null;
    reach?: Record<ReachChannel, Reach>;  // phase 4: may be missing while the backend deploys
    permissions?: Permission[];
    promises?: LeadPromise[];              // phase 7: the same
    promise_how?: Record<string, string>;
}

export type ReachChannel = "call" | "whatsapp" | "email";

/** Whether something automatic may reach them on a channel now (backend leads/contact.py), and why not. */
export interface Reach {
    ok: boolean;
    reason: string;
    code: string;
    cause: string;
    wait_until: string | null;
}

/** What they said about being contacted, with where it came from. */
export interface Permission {
    channel: ReachChannel;
    purpose: string;
    state: "granted" | "refused";
    source: string;
    words: string | null;
    given_at: string | null;
    expires_at: string | null;
}

export const REACH_LABEL: Record<ReachChannel, string> = { call: "Calls from the assistant", whatsapp: "WhatsApp messages", email: "Emails" };

export interface LeadReport {
    days: number;
    leads: number;
    junk: number;
    sources: { source: string; leads: number; reached: number; meetings: number; won: number; lost: number; value: number; junk: number }[];
    first_response: { measured: number; median_minutes: number | null; within_5: number; within_60: number; not_tried: number };
    team: { id: string; name: string; done: number; overdue: number; won: number }[];
    won: number;
    lost: number;
    value: number;
    lost_reasons: { reason: string; count: number }[];
    lost_by_source?: { source: string; lost: number; reasons: { reason: string; count: number }[] }[];  // phase 7
    promises?: { made: number; kept: number; on_time: number; cancelled: number; late: number; by_channel: { made_on: string; made: number; kept: number; on_time: number }[] };
}

export interface LeadRouting {
    settings: {
        assign: "off" | "one" | "turns"; people: string[]; backup: string | null; first_task: boolean; respond_minutes: number;
        // WhatsApp templates (phase 4): missing while an older backend answers
        whatsapp_first?: string | null; whatsapp_language?: string; alert_template?: string | null; alert_language?: string;
    };
    team: Person[];
}

/** A date-time input's value for a moment, in the viewer's own time. */
export function localInput(at: Date) {
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}T${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

/** When a task is due or a meeting starts, before or after now: "Today, 4:30 pm", "Tomorrow, 10:00 am", "5 Nov, 10:00 am". */
/** formatDue inside a sentence: "due today, 4:30 pm". */
export function dueInline(iso: string) {
    return formatDue(iso).replace(/^(Today|Tomorrow|Yesterday)/, (x) => x.toLowerCase());
}

export function formatDue(iso: string) {
    const d = parseUtc(iso);
    const time = d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
    const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const days = Math.round((day(d) - day(new Date())) / 86_400_000);
    const named: Record<number, string> = { [-1]: "Yesterday", 0: "Today", 1: "Tomorrow" };
    return `${named[days] ?? d.toLocaleDateString("en-IN", { day: "numeric", month: "short" })}, ${time}`;
}

/** A time from formatWhen or formatDue inside a sentence: "Asked today, 4:23 am", "Last lead just now". */
export function inline(text: string) {
    return text.charAt(0).toLowerCase() + text.slice(1);
}

export function rupees(amount: number) {
    return `Rs ${amount.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}
