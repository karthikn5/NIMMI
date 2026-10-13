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

export interface VoiceAgentConfig {
    bot_id: string;
    bot_name: string;
    enabled: boolean;
    language: LanguageCode;
    understand_code_mixed: boolean;
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

export interface MinutePack {
    id: string;
    minutes: number;
    price: number; // INR, excl. GST
}

export interface VoiceOverview {
    minutes_included: number;
    minutes_used: number;
    minutes_topup: number;
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
