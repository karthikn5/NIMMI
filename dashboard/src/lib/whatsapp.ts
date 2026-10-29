"use client";

import { useEffect, useState } from "react";
import { activeOwnerId, apiJson } from "@/lib/api";

/** How the assistant behaves on a WhatsApp number (backend whatsapp/settings.py). */
export type WaSettings = {
    wait_seconds: number;
    typing: boolean;
    split: boolean;
    length: "short" | "normal";
    understand_media: boolean;
    send_files: boolean;
    buttons: boolean;
    pause_hours: number;
    welcome: string;
};

export type WaNumber = {
    id: string;
    phone_number_id: string;
    waba_id: string;
    display_number: string | null;
    verified_name: string | null;
    bot_id: string;
    bot_name: string | null;
    ai_enabled: boolean;
    settings: WaSettings;
    connection: "manual" | "signup";
    status: "connected" | "error" | "disconnected";
    status_detail: string | null;
    quality_rating: string | null;
    messaging_limit: string | null;
    has_token: boolean;
    has_app_secret: boolean;
    verify_token: string | null;
    webhook_url: string | null;
    last_inbound_at: string | null;
    created_at: string | null;
    replies_this_month?: number;
    free_left?: number;
};

export type WaChat = {
    id: string;
    number_id: string;
    bot_id: string | null;
    conversation_id: string | null;
    name: string;
    profile_name: string | null;
    phone: string | null;
    status: "open" | "closed";
    unread: number;
    assigned_to: string | null;
    ai_paused_until: string | null;
    window_ends: string | null;
    last_message_at: string | null;
    last: { role: string; text: string; by: "customer" | "ai" | "team" } | null;
    handoff?: "ai" | "pending" | "human";
};

export type WaMessage = {
    id: string;
    role: "user" | "assistant" | "note";
    text: string;
    at: string | null;
    kind: string;
    sent_by: "customer" | "ai" | "team" | "phone" | "note";
    author: string | null;
    status: "received" | "sent" | "delivered" | "read" | "failed" | null;
    error: string | null;
    media: { mime?: string; filename?: string; caption?: string; size?: number; url?: string } | null;
    wa_message_id: string | null;
};

export type WaChatDetail = WaChat & {
    handoff: "ai" | "pending" | "human";
    captured: Record<string, string>;
    number: { id: string; display_number: string | null; status: string } | null;
    summary: string | null;
    messages: WaMessage[];
};

export type WaFile = {
    id: string;
    name: string;
    when_to_send: string;
    caption: string;
    kind: "image" | "video" | "audio" | "document";
    mime: string;
    filename: string;
    size: number;
    bot_id: string;
    bot_name: string | null;
    sends: number;
    created_at: string | null;
    url: string;
};

export type WaOverview = {
    numbers: WaNumber[];
    month: { chats: number; from_customers: number; by_ai: number; by_team: number; waiting_for_team: number };
    setup: { connected: boolean; answering: boolean; app_secret: boolean; files: number; first_message: boolean; free_replies: number };
};

export type Person = { id: string; name: string };

/** Meta's India rate per reply after the free 1,000 a month (Oct 2026); shown as a guide, Meta bills it. */
export const REPLY_RATE_INR = 0.115;
export const PAUSE_CHOICES = [1, 4, 12, 24, 72];

/** The signed-in person's role in the workspace they're looking at. */
export function useRole(): "owner" | "admin" | "agent" | null {
    const [role, setRole] = useState<"owner" | "admin" | "agent" | null>(null);
    useEffect(() => {
        apiJson<{ owner_id: string; role: "owner" | "admin" | "agent" }[]>("/api/team/workspaces")
            .then((list) => setRole((list.find((w) => w.owner_id === activeOwnerId()) ?? list[0])?.role ?? "owner"))
            .catch(() => setRole("owner"));
    }, []);
    return role;
}

/** "5 h 12 min" until the 24-hour window ends. */
export function timeLeft(iso: string | null): string {
    if (!iso) return "";
    const ms = new Date(iso).getTime() - Date.now();
    if (ms <= 0) return "";
    const h = Math.floor(ms / 3_600_000);
    const m = Math.floor((ms % 3_600_000) / 60_000);
    return h ? `${h} h ${m} min` : `${m} min`;
}

export function fileKind(f: { kind: string; mime: string }): string {
    if (f.mime === "application/pdf") return "PDF";
    return { image: "Photo", video: "Video", audio: "Audio", document: "Document" }[f.kind] ?? "File";
}
