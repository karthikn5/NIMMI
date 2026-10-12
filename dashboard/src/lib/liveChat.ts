"use client";

import { useEffect, useSyncExternalStore } from "react";
import { io, type Socket } from "socket.io-client";
import { activeOwnerId, apiBase, apiJson, getToken } from "@/lib/api";

/**
 * One shared live-chat connection per page: how many visitors are waiting
 * for a person, kept current over the socket.
 */
let waiting = 0;
let socket: Socket | null = null;
const listeners = new Set<() => void>();

async function refresh() {
    try {
        const list = await apiJson<{ session_id: string; status: string }[]>("/api/handoffs/pending");
        // Only chats nobody has picked up yet; ones being handled aren't "waiting".
        waiting = list.filter((h) => h.status === "pending" && h.session_id.startsWith("widget-session-human-")).length;
        listeners.forEach((l) => l());
    } catch { /* non-critical */ }
}

function connect() {
    if (socket || !getToken()) return;
    socket = io(apiBase(), { transports: ["websocket"] });
    socket.on("connect", () => socket?.emit("join", { room: `admin_${activeOwnerId()}`, token: getToken() }));
    socket.on("handoff_requested", refresh);
    refresh();
}

export function useWaitingCount() {
    useEffect(connect, []);
    return useSyncExternalStore(
        (cb) => { listeners.add(cb); return () => listeners.delete(cb); },
        () => waiting,
        () => 0,
    );
}

/** The shared socket, for pages that need more events (the live chat inbox). */
export function liveSocket(): Socket | null {
    connect();
    return socket;
}

export const refreshWaiting = refresh;
