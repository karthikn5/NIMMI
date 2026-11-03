"use client";

/** How the assistant behaves on an Instagram account (backend instagram/settings.py). */
export type IgSettings = {
    wait_seconds: number;
    typing: boolean;
    split: boolean;
    length: "short" | "normal";
    understand_media: boolean;
    buttons: boolean;
    pause_hours: number;
    welcome: string;
};

export type IgAccount = {
    id: string;
    ig_id: string;
    username: string | null;
    name: string | null;
    bot_id: string;
    bot_name: string | null;
    ai_enabled: boolean;
    settings: IgSettings;
    status: "connected" | "token" | "permission" | "disconnected";
    status_detail: string | null;
    subscribed: boolean;
    token_expires_at: string | null;
    last_inbound_at: string | null;
    created_at: string | null;
    missing?: string[];
    comments_allowed?: boolean;  // phase 6: missing while an older backend answers
    profile?: { ice_breakers: string[]; menu: { title: string; url?: string }[]; error?: string | null };
};

/** A comment rule (backend instagram/comments.py), with what it led to. */
export type IgRule = {
    id: string;
    account_id: string;
    name: string;
    media_ids: string[];
    keywords: string[];
    private_reply: string;
    public_replies: string[];
    enabled: boolean;
    last_error: string | null;
    last_error_at: string | null;
    report: { comments: number; private_replies: number; public_replies: number; conversations: number; leads: number; sales: number; value: number };
    created_at: string | null;
};

export type IgComment = {
    id: string;
    username: string | null;
    text: string | null;
    media_id: string | null;
    rule_id: string | null;
    status: "new" | "working" | "replied" | "skipped" | "failed";
    why: string | null;
    public: boolean;
    at: string | null;
};

export type IgMedia = { id: string; caption: string; type: string | null; permalink: string | null; picture: string | null; at: string | null };

/** An ig.me link that opens a chat with the account, with a ref saying where the person found it (letters, digits, -, _ and = only). */
export function igMeLink(username: string, ref: string): string {
    const clean = ref.replace(/[^A-Za-z0-9_=-]/g, "");
    return `https://ig.me/m/${username}${clean ? `?ref=${clean}` : ""}`;
}

export type IgOverview = {
    available: boolean;
    accounts: IgAccount[];
    month: { chats: number; answered: number; waiting: number };
};

/** How a person's reply may go now: as usual (24 hours), with Instagram's human agent tag (up to 7 days), or not at all. */
export type IgRoute = "open" | "human_agent" | "closed";

export type IgChat = {
    id: string;
    account_id: string;
    bot_id: string | null;
    conversation_id: string | null;
    contact_id: string | null;
    name: string;
    username: string | null;
    full_name: string | null;
    status: "open" | "closed";
    unread: number;
    assigned_to: string | null;
    ai_paused_until: string | null;
    window_ends: string | null;
    human_window_ends: string | null;
    reply: IgRoute;
    last_message_at: string | null;
    last: { role: string; text: string; by: "customer" | "ai" | "team" } | null;
    handoff?: "ai" | "pending" | "human";
};

export type IgMessage = {
    id: string;
    role: "user" | "assistant" | "note";
    text: string;
    at: string | null;
    kind: string;
    sent_by: "customer" | "ai" | "team" | "app" | "note";
    author: string | null;
    status: "received" | "sending" | "sent" | "read" | "failed" | "deleted" | null;
    error: string | null;
    media: { type?: string; mime?: string; url?: string } | null;
    tag: string | null;
    ig_message_id: string | null;
};

export type IgChatDetail = IgChat & {
    handoff: "ai" | "pending" | "human";
    captured: Record<string, string>;
    account: { id: string; username: string | null; status: string } | null;
    messages: IgMessage[];
};

export const STATUS: Record<IgAccount["status"], { tone: "good" | "warn" | "bad" | "neutral"; text: string }> = {
    connected: { tone: "good", text: "Connected" },
    token: { tone: "bad", text: "Connect again" },
    permission: { tone: "warn", text: "Needs a permission" },
    disconnected: { tone: "neutral", text: "Disconnected" },
};

export const PAUSE_CHOICES = [1, 4, 12, 24, 72];
