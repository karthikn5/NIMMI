// Data contract for the Voice module; mirrors backend/voice/router.py.

export type LanguageCode =
    | "en-IN" | "hi-IN" | "ta-IN" | "te-IN" | "kn-IN" | "ml-IN"
    | "mr-IN" | "bn-IN" | "gu-IN" | "pa-IN" | "od-IN";

export interface Voice {
    id: string;
    name: string;
    gender: "female" | "male";
    tone?: string;
    sample_url?: string;
}

export interface VoiceAgentSummary {
    bot_id: string;
    bot_name: string;
    enabled: boolean;
    language: LanguageCode;
    voice_id: string | null;
    phone_number: string | null;
    calls_30d: number;
}

/** Each assistant has two voice agents: one answers calls, one makes them. */
export type AgentDirection = "inbound" | "outbound";

export interface VoiceAgentConfig {
    bot_id: string;
    bot_name: string;
    direction: AgentDirection;
    enabled: boolean;
    language: LanguageCode;
    understand_code_mixed: boolean;
    follow_caller_language: boolean;   // answer in the caller's language when they speak another one
    switch_languages: LanguageCode[];  // the only languages it may change to; empty = any
    remember_callers: boolean;         // caller memory, for both agents of the assistant
    voice_id: string | null;
    speaking_rate: number; // 0.8 – 1.2
    assistant_name: string; // how the agent introduces itself
    company_name: string;
    greeting: string;
    allow_interruptions: boolean;
    silence_timeout_sec: number;
    max_call_minutes: number;
    transfer_enabled: boolean;
    transfer_number: string;
    transfer_when: string;
    end_call_phrases: string[];
    call_goal: string;                 // what a successful call looks like; judged after each call
    collect_fields: CollectField[];    // what the assistant finds out; stored per call
    ambience: AmbienceKind;
    ambience_volume: "subtle" | "low" | "medium" | "high";
    silence_reminders: number;         // 0-3 "are you still there?" prompts before hanging up
    pronunciations: { word: string; say: string }[];
    voicemail_action: "off" | "hangup" | "leave_message";
    voicemail_message: string;
    transfer_mode: "cold" | "warm";
    team_handoff: boolean;             // ring the team in the dashboard when a caller needs a person
    team_handoff_wait: number;         // seconds to wait for someone to pick up
    ai_model: string;                  // VoiceModel id
    functions: AgentFunction[];        // what it can do during a call (backend voice/functions.py)
}

export interface FunctionParameter {
    name: string;
    type: "string" | "number" | "boolean" | "enum";
    description: string;
    required: boolean;
    choices: string[];
}

/** One thing the agent can do during a call. Secrets come back masked ("••••1234"); sent back unchanged, they're kept. */
export interface AgentFunction {
    id?: string;
    kind: "custom" | "check_slots" | "book";
    name: string;                      // lowercase_with_underscores
    description: string;               // when the agent should use it
    enabled: boolean;
    speak_during: string;              // said while it runs, if the agent hasn't spoken yet
    url?: string;                      // custom: {{caller_number}} and other placeholders work
    method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
    parameters?: FunctionParameter[];
    headers?: { name: string; value: string }[];
    timeout_sec?: number;
    cal_api_key?: string;              // check_slots, book
    event_type_id?: number | string;
    timezone?: string;
}

export type AmbienceKind =
    | "none"
    | "subtle_room"
    | "quiet_office"
    | "call_center"
    | "executive_suite"
    | "cafe"
    | "comfort_noise"
    | "office"
    | "street"
    | "static";
export type FieldType = "text" | "number" | "yes_no" | "choice" | "date" | "phone" | "email";

export interface CollectField {
    key?: string;
    label: string;
    type: FieldType;
    description: string;
    choices: string[];
    required: boolean;
}

export type CallDirection = "inbound" | "outbound";
export type CallOutcome = "lead_captured" | "answered" | "transferred" | "no_answer" | "voicemail" | "opted_out" | "failed";
export type Sentiment = "positive" | "neutral" | "negative";

export interface TranscriptTurn {
    at_sec: number;
    speaker: "agent" | "caller" | "system";
    text: string;
}

export interface CallRecord {
    id: string;
    started_at: string; // ISO, UTC
    direction: CallDirection;
    channel: "phone" | "browser";
    in_progress?: boolean;
    caller: string;     // masked in lists, full in detail
    bot_id: string;
    bot_name: string;
    duration_sec: number;
    outcome: CallOutcome;
    language: LanguageCode;
    summary?: string;
    recording_url?: string | null;
    captured?: Record<string, string>;
    consent_source?: string; // outbound only: where the caller asked for a callback
    transcript?: TranscriptTurn[];
    successful?: boolean | null;  // reached the agent's goal (post-call analysis)
    sentiment?: Sentiment | null;
    campaign_id?: string | null;
    credits_used?: number | null; // null: from before credits
    ai_model?: string | null;     // the model's name
    reply_sec?: number | null;    // median time from the caller stopping to the agent's first sound
}

export interface CollectedRow {
    call_id: string;
    started_at: string;
    direction: CallDirection;
    channel: "phone" | "browser";
    caller: string;
    outcome: CallOutcome;
    successful: boolean | null;
    sentiment: Sentiment | null;
    summary: string;
    duration_sec: number;
    values: Record<string, string>;
    campaign_id: string | null;
    lead: { score: number; label: "hot" | "warm" | "cold"; reasons: string[] };
}

export type CampaignStatus = "running" | "paused" | "completed" | "cancelled";

export interface CampaignSummary {
    id: string;
    name: string;
    bot_id: string;
    bot_name: string;
    purpose: string;
    status: CampaignStatus;
    from_number: string | null;
    window_start: string;
    window_end: string;
    max_attempts: number;
    concurrency: number;
    created_at: string;
    completed_at: string | null;
    counts: { total: number; queued: number; calling: number; done: number; failed: number; cancelled: number; successful: number };
}

export interface CampaignContact {
    id: string;
    phone: string;
    name: string | null;
    variables: Record<string, string>;
    status: CallbackJob["status"];
    attempts: number;
    last_error: string | null;
    next_attempt_at: string | null;
    call_id: string | null;
    outcome: CallOutcome | null;
    successful: boolean | null;
    sentiment: Sentiment | null;
    summary: string | null;
    values: Record<string, string>;
}

export interface CampaignDetail extends CampaignSummary {
    fields: string[];
    contacts: CampaignContact[];
}

export interface PhoneNumber {
    id: string;
    number: string;
    kind: "landline" | "mobile" | "local" | "toll_free";
    city: string;
    status: "active" | "pending_kyc" | "provisioning" | "suspended";
    bot_id: string | null;
    monthly_fee: number;
    provider: "exotel" | "twilio";
    country: string | null;      // self-serve numbers only (ISO code)
    next_charge_at: string | null; // self-serve numbers: next monthly charge from the balance
    documents: ("coi" | "gst")[];
    source: "nimmi" | "own";       // bought from Nimmi, or on the customer's own Twilio/Exotel account
    account_id: string | null;
    can_replace: boolean;          // Nimmi-bought number that can be swapped for a new one now
}

/** A customer's own Twilio or Exotel account connected to Nimmi. */
export interface PhoneAccount {
    id: string;
    provider: "twilio" | "exotel";
    label: string;
    account_sid: string;           // masked
    numbers: number;
    created_at: string | null;
    subdomain?: string;
    app_id?: string;
    setup?: { voicebot: string; after_bot: string; transfer_target: string };
}

export interface AccountNumber {
    phone_number: string;
    display: string;
    name: string;
    country: string;
    connected: boolean;
    in_use: boolean;
    has_other_webhook: boolean;
}

export interface NumberCountry {
    code: string;
    name: string;
    types: ("local" | "toll_free" | "mobile")[];
}

export interface AvailableNumber {
    phone_number: string; // E.164
    display: string;
    friendly_name: string;
    locality: string;
    region: string;
    address_required: boolean;
}

export interface CallbackJob {
    id: string;
    number: string;
    name: string | null;
    status: "queued" | "calling" | "done" | "failed" | "cancelled";
    attempts: number;
    next_attempt_at: string | null;
    last_error: string | null;
    call_id: string | null;
    created_at: string | null;
}

export interface CallbackSettings {
    enabled: boolean;
    delay: "immediate" | "1m" | "5m" | "15m";
    window_start: string; // "09:00"
    window_end: string;   // "21:00"
    max_attempts: number;
    from_number_id: string | null;
}

export interface ComplianceSettings {
    disclosure_enabled: true; // always on, not configurable
    record_calls: boolean;
    retention_days: 30 | 90 | 180;
    opt_out_phrases: string[];
}

export interface DncEntry {
    id: string;
    number: string;
    reason: "caller_request" | "manual" | "imported";
    added_at: string;
}

export interface CreditPack {
    id: string;
    credits: number;
    price: number; // INR, excl. GST
}

/** An AI model an agent can answer with (backend voice/ai_models.py). */
export interface VoiceModel {
    id: string;
    name: string;
    maker: string;
    group: "fast" | "smart";
    about: string;
    credits_per_minute: number;       // the whole call minute: voice and phone line plus the model
    model_credits: number;            // the model's part of it
    first_words_sec: number | null;   // measured; null until it has been
    available: boolean;               // false: not set up on the server yet
    suggested: boolean;
    preview: boolean;                 // its service may change or remove it
    functions: boolean;               // can run the agent's functions
    minutes_left?: number;            // what the workspace's credits pay for on it
}

export interface RateCard {
    base_credits: number;
    billing_step_sec: number;
    free_credits: number;
    groups: Record<VoiceModel["group"], string>;
    packs: CreditPack[];
    models: VoiceModel[];
}

export interface VoiceModels extends RateCard {
    credits_left: number;
    default: string;
}

/** The agent page's summary line (GET /api/voice/agents/{bot}/details). */
export interface AgentDetails {
    model: VoiceModel;
    credits_per_minute: number;
    base_credits: number;
    prompt_tokens: number;            // the instructions and knowledge that go with every answer
    reply_sec_expected: number | null;
    reply_sec_measured: number | null; // median over its recent calls
    calls_measured: number;
}

export interface VoiceOverview {
    credits_left: number;
    credits_included: number;   // a plan's credits this month
    credits_used: number;       // of those
    credits_bought: number;     // bought and free credits; they don't expire
    cycle_ends: string | null;
    calls_this_month: number;
    calls_last_month: number;
    ai_resolved_pct: number;
    avg_duration_sec: number;
    leads_captured: number;
    calls_by_day: { date: string; count: number }[];
    setup: {
        voice_chosen: boolean;
        tested_in_browser: boolean;
        number_active: boolean;
        callbacks_on: boolean;
    };
    engine_ready: boolean;
    phone_ready: boolean;
}

/** What an agent says on one kind of call (Voice > Knowledge). */
export interface VoiceScript {
    bot_id: string;
    bot_name: string;
    direction: AgentDirection;
    saved: boolean;                    // false: still the agent's own opening, goal and fields
    language: LanguageCode;
    assistant_name: string;
    company_name: string;
    greeting: string;                  // after the required "automated, may be recorded" line
    greeting_known: string;            // for someone it has spoken to before; {{name}} is their first name
    personality: string;               // a preset key, or the owner's own words
    instructions: string;
    call_goal: string;
    collect_fields: CollectField[];
    answers: ScriptAnswer[];           // what "Write with AI" was told
}

export interface ScriptAnswer {
    question: string;
    answer: string;
}

export type ScriptDraft = Pick<VoiceScript, "greeting" | "greeting_known" | "personality" | "instructions" | "call_goal" | "collect_fields">;

/** Someone an assistant has spoken to on the phone, by number (Voice > Contacts). */
export interface ContactSummary {
    id: string;
    bot_id: string;
    bot_name: string;
    number: string;                    // masked in lists, full in detail
    name: string;
    calls: number;
    last_call_at: string | null;
    notes: string;
    lead_status: LeadStatus | null;    // rated after each call (Voice > Schedule), or set by the team
    lead_reason: string;
    lead_set_by_team: boolean;
    follow_ups: number;
    follow_ups_off: boolean;
}

export interface ContactDetail extends ContactSummary {
    email: string;
    details: Record<string, string>;
    first_call_at: string | null;
    remember_from: string | null;
    history: { id: string; started_at: string | null; direction: CallDirection; outcome: CallOutcome; summary: string; remembered: boolean }[];
}

/* ---------- Schedule: call-backs, follow-ups and meetings (backend voice/schedule.py) ---------- */

export type LeadStatus = "hot" | "warm" | "cold" | "new" | "not_interested" | "customer";
export type FollowedUp = "hot" | "warm" | "cold" | "new";
export type MeetingKind = "online" | "in_person" | "phone";
export type MeetingStatus = "requested" | "proposed" | "confirmed" | "cancelled" | "expired" | "done" | "no_show";
export type ScheduleKind = "callback" | "follow_up" | "meeting" | "no_show" | "person";
export type ScheduleStatus = "queued" | "review" | "calling" | "todo" | "done" | "failed" | "cancelled";
export type Weekday = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";

export interface ScheduleSettings {
    timezone: string;
    from_number_id: string | null;     // null: the number they called
    callbacks: { enabled: boolean; hours: [string, string]; attempts: number; retry_minutes: number };
    follow_ups: {
        enabled: boolean;
        review: boolean;               // each one waits for the team's OK
        hours: [string, string];
        days: Weekday[];
        rules: Record<FollowedUp, { count: number; every: number }>;
        stop_after_days: number;
        max_total: number;
        attempts: number;
    };
    meetings: {
        enabled: boolean;
        approval: boolean;
        kinds: MeetingKind[];
        minutes: number;
        days: Weekday[];
        hours: [string, string];
        notice_hours: number;
        ahead_days: number;
        at_once: number;
        offer_when: string;
        link: string;
        address: string;
        confirm_call: boolean;
        link_minutes: number;
        day_before: boolean;
        no_show_call: boolean;
        whatsapp_template: string;
        template_language: string;
    };
}

export interface ScheduleSettingsView {
    settings: ScheduleSettings;
    numbers: { id: string; number: string; own: boolean }[];
    whatsapp: boolean;
}

export interface ScheduleItem {
    id: string;
    kind: ScheduleKind;
    bot_id: string;
    bot_name: string;
    from: "website" | "team" | "assistant";
    name: string;
    number: string;
    status: ScheduleStatus;
    due_at: string | null;
    local: string | null;              // YYYY-MM-DDTHH:MM in the assistant's time zone
    timezone: string;
    purpose: string;
    attempts: number;
    last_error: string | null;
    call_id: string | null;            // the call it led to
    source_call_id: string | null;     // the call it was arranged on
    meeting_id: string | null;
    step: number | null;
    consent: string;
    created_at: string | null;
    result: { outcome: CallOutcome; summary: string } | null;
}

export interface MeetingSummary {
    id: string;
    bot_id: string;
    bot_name: string;
    name: string;
    number: string;
    kind: MeetingKind;
    topic: string;
    starts_at: string;
    local: string;
    minutes: number;
    status: MeetingStatus;
    link: string;                      // its own link or address
    place: string;                     // what they'll get: its link, or the default one; the address
    host_id: string | null;
    timezone: string;
    sent: Record<string, { at: string; via: string[] }>;
    created_at: string | null;
}

export interface MeetingDetail extends MeetingSummary {
    email: string;
    notes: string;
    history: { at: string; what: string; by: string | null }[];
    source_call_id: string | null;
    source_call: { id: string; summary: string; started_at: string | null } | null;
    messages: { kind: string; status: string; note: string | null; at: string | null }[];
    calls: { id: string; kind: string; status: ScheduleStatus; due_at: string | null; about: string | null; last_error: string | null; call_id: string | null }[];
    channels: { whatsapp: "window" | "template" | null; email: boolean };
    setup: { confirm_call: boolean; link_minutes: number; default_link: string; address: string; template: boolean };
}

export interface ScheduleAttention { approve: number; review: number; people: number; mark: number; total: number }

export interface ScheduleOverview {
    attention: ScheduleAttention;
    stats: {
        callbacks: { booked: number; reached: number; missed: number };
        follow_ups: { made: number; answered: number };
        meetings: { requested: number; confirmed: number; attended: number; missed: number };
        leads: Partial<Record<LeadStatus, number>>;
    };
    calls: ScheduleItem[];
    meetings: MeetingSummary[];
    people: ScheduleItem[];
    missed: ScheduleItem[];
    to_mark: MeetingSummary[];
}

export interface ScheduleHost { id: string; name: string; email: string }
