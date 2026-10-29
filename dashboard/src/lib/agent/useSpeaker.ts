"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";

/** Reads an answer aloud (Nimmi's voice service, in the language the answer is written in). One at a time. */
export function useSpeaker(onError: (message: string) => void) {
    const [playing, setPlaying] = useState<string | null>(null);
    const [loading, setLoading] = useState<string | null>(null);
    const current = useRef<{ audio: HTMLAudioElement; url: string } | null>(null);

    const stop = useCallback(() => {
        if (current.current) {
            current.current.audio.pause();
            URL.revokeObjectURL(current.current.url);
            current.current = null;
        }
        setPlaying(null);
    }, []);

    useEffect(() => stop, [stop]);

    const speak = useCallback(async (id: string, text: string) => {
        if (playing === id) { stop(); return; }
        stop();
        setLoading(id);
        try {
            const res = await apiFetch("/api/agent/speak", { method: "POST", json: { text } });
            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                throw new Error(typeof body.detail === "string" ? body.detail : "Couldn't read that aloud.");
            }
            const url = URL.createObjectURL(await res.blob());
            const audio = new Audio(url);
            current.current = { audio, url };
            audio.onended = () => stop();
            setPlaying(id);
            await audio.play();
        } catch (e) {
            stop();
            onError((e as Error).message || "Couldn't read that aloud.");
        } finally {
            setLoading(null);
        }
    }, [onError, playing, stop]);

    return { playing, loading, speak, stop };
}
