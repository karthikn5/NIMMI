"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";

/**
 * The agent panel's mic: records a short message (up to a minute), shows how loud it is while listening, then has
 * Nimmi's speech service (Sarvam: Indian languages and mixes like Tanglish) write it out. The text goes into the
 * message box for the person to check before sending.
 */
export type RecorderState = "idle" | "starting" | "recording" | "transcribing";
const MAX_SECONDS = 60;

function mimeType(): string {
    if (typeof MediaRecorder === "undefined") return "";
    return ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"].find((t) => MediaRecorder.isTypeSupported(t)) ?? "";
}

export function useRecorder(onText: (text: string) => void, onError: (message: string) => void) {
    const [state, setState] = useState<RecorderState>("idle");
    const [seconds, setSeconds] = useState(0);
    const [level, setLevel] = useState(0);
    const [supported, setSupported] = useState(false);
    const recorder = useRef<MediaRecorder | null>(null);
    const stream = useRef<MediaStream | null>(null);
    const audio = useRef<AudioContext | null>(null);
    const chunks = useRef<Blob[]>([]);
    const keep = useRef(true);
    const timers = useRef<{ tick?: ReturnType<typeof setInterval>; frame?: number }>({});

    useEffect(() => {
        setSupported(typeof window !== "undefined" && window.isSecureContext && !!navigator.mediaDevices?.getUserMedia
                     && typeof MediaRecorder !== "undefined");
    }, []);

    const cleanUp = useCallback(() => {
        if (timers.current.tick) clearInterval(timers.current.tick);
        if (timers.current.frame) cancelAnimationFrame(timers.current.frame);
        timers.current = {};
        stream.current?.getTracks().forEach((t) => t.stop());
        stream.current = null;
        void audio.current?.close().catch(() => {});
        audio.current = null;
        setLevel(0);
    }, []);

    useEffect(() => cleanUp, [cleanUp]);

    const send = useCallback(async (blob: Blob) => {
        setState("transcribing");
        const form = new FormData();
        form.append("file", blob, blob.type.includes("mp4") ? "speech.mp4" : "speech.webm");
        try {
            const res = await apiFetch("/api/agent/transcribe", { method: "POST", body: form });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Couldn't write that out.");
            if (body.text) onText(body.text);
            else onError("I didn't catch anything. Try again a little closer to the mic.");
        } catch (e) {
            onError((e as Error).message || "Couldn't write that out.");
        } finally {
            setState("idle");
        }
    }, [onError, onText]);

    const start = useCallback(async () => {
        if (state !== "idle") return;
        setState("starting");
        try {
            stream.current = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
        } catch (e) {
            setState("idle");
            const denied = (e as Error).name === "NotAllowedError";
            onError(denied ? "The microphone is blocked. Allow it for this site (the icon at the left of the address bar), then try again."
                           : "No microphone was found.");
            return;
        }
        const type = mimeType();
        const rec = new MediaRecorder(stream.current, type ? { mimeType: type } : undefined);
        recorder.current = rec;
        chunks.current = [];
        keep.current = true;
        rec.ondataavailable = (e) => { if (e.data.size) chunks.current.push(e.data); };
        rec.onstop = () => {
            const blob = new Blob(chunks.current, { type: rec.mimeType || type || "audio/webm" });
            cleanUp();
            if (!keep.current) setState("idle");
            else if (blob.size > 300) void send(blob);
            else { setState("idle"); onError("I didn't hear anything. Check the mic, then try again."); }
        };
        rec.start(250);
        setSeconds(0);
        setState("recording");
        const began = Date.now();
        timers.current.tick = setInterval(() => {
            const s = Math.floor((Date.now() - began) / 1000);
            setSeconds(s);
            if (s >= MAX_SECONDS && rec.state === "recording") rec.stop();
        }, 250);
        // How loud it is, for the bars while listening.
        try {
            const ctx = new AudioContext();
            audio.current = ctx;
            const analyser = ctx.createAnalyser();
            analyser.fftSize = 512;
            ctx.createMediaStreamSource(stream.current).connect(analyser);
            const data = new Uint8Array(analyser.fftSize);
            const draw = () => {
                analyser.getByteTimeDomainData(data);
                let sum = 0;
                for (const v of data) sum += ((v - 128) / 128) ** 2;
                setLevel(Math.min(1, Math.sqrt(sum / data.length) * 4));
                timers.current.frame = requestAnimationFrame(draw);
            };
            draw();
        } catch { /* no meter: recording still works */ }
    }, [cleanUp, onError, send, state]);

    /** Stop listening; `keepIt` false throws the recording away. */
    const stop = useCallback((keepIt = true) => {
        keep.current = keepIt;
        if (recorder.current?.state === "recording") recorder.current.stop();
    }, []);

    return { state, seconds, level, supported, start, stop };
}
