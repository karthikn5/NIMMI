/**
 * Voice input for the chat widget's mic button.
 *
 * Uses the browser's own speech recognition when it has one (Chrome, Edge, Safari): instant,
 * free, and the words appear while the visitor speaks. Otherwise it records a short clip and
 * sends it to the server, which transcribes it with Sarvam (good with Indian languages).
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const MAX_RECORDING_MS = 30_000;

/** BCP-47 language for recognition, from the assistant's Behaviour language. */
export function speechLang(language?: string): string {
    const map: Record<string, string> = {
        en: "en-IN", hi: "hi-IN", ta: "ta-IN", te: "te-IN", kn: "kn-IN", ml: "ml-IN", mr: "mr-IN", bn: "bn-IN", gu: "gu-IN",
    };
    return (language && map[language]) || "en-IN";
}

type Recognition = {
    lang: string; interimResults: boolean; continuous: boolean; maxAlternatives: number;
    start(): void; stop(): void; abort(): void;
    onresult: ((e: any) => void) | null; onerror: ((e: any) => void) | null; onend: (() => void) | null;
};

function recognitionClass(): (new () => Recognition) | null {
    if (typeof window === "undefined") return null;
    const w = window as any;
    return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export function useVoiceInput({ lang, apiBase, botId, headers, onText, onError }: {
    lang: string; apiBase: string; botId: string; headers?: Record<string, string>;
    /** Called with the words so far (final = false) and once with the finished text (final = true). */
    onText: (text: string, final: boolean) => void;
    onError: (message: string) => void;
}) {
    const [listening, setListening] = useState(false);
    const [busy, setBusy] = useState(false); // transcribing a recording
    const [supported, setSupported] = useState(false);
    const recognition = useRef<Recognition | null>(null);
    const recorder = useRef<MediaRecorder | null>(null);
    const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const latest = useRef({ onText, onError });
    latest.current = { onText, onError };

    useEffect(() => {
        setSupported(!!recognitionClass() || (typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia
            && typeof MediaRecorder !== "undefined"));
    }, []);

    const stop = useCallback(() => {
        if (timer.current) clearTimeout(timer.current);
        recognition.current?.stop();
        if (recorder.current?.state === "recording") recorder.current.stop();
    }, []);

    const startRecognition = useCallback((Cls: new () => Recognition) => {
        const r = new Cls();
        r.lang = lang;
        r.interimResults = true;
        r.continuous = false;
        r.maxAlternatives = 1;
        let finalText = "";
        r.onresult = (e: any) => {
            let interim = "";
            for (let i = e.resultIndex; i < e.results.length; i++) {
                const piece = e.results[i][0]?.transcript || "";
                if (e.results[i].isFinal) finalText += piece; else interim += piece;
            }
            latest.current.onText((finalText + interim).trim(), false);
        };
        r.onerror = (e: any) => {
            if (e?.error === "not-allowed" || e?.error === "service-not-allowed") latest.current.onError("Please allow the microphone, or type your message.");
            else if (e?.error && e.error !== "no-speech" && e.error !== "aborted") latest.current.onError("Couldn't hear that clearly. Please try again or type your message.");
        };
        r.onend = () => {
            setListening(false);
            recognition.current = null;
            if (finalText.trim()) latest.current.onText(finalText.trim(), true);
        };
        recognition.current = r;
        setListening(true);
        r.start();
        timer.current = setTimeout(() => r.stop(), MAX_RECORDING_MS);
    }, [lang]);

    const startRecording = useCallback(async () => {
        let stream: MediaStream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch {
            latest.current.onError("Please allow the microphone, or type your message.");
            return;
        }
        const rec = new MediaRecorder(stream);
        const chunks: Blob[] = [];
        rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
        rec.onstop = async () => {
            stream.getTracks().forEach((t) => t.stop());
            setListening(false);
            const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
            if (!blob.size) return;
            setBusy(true);
            try {
                const form = new FormData();
                form.append("bot_id", botId);
                form.append("file", blob, `speech.${(rec.mimeType || "audio/webm").split("/")[1].split(";")[0]}`);
                const res = await fetch(`${apiBase}/api/chat/transcribe`, { method: "POST", body: form, headers: headers || {} });
                const body = await res.json().catch(() => ({}));
                if (res.ok && body.text) latest.current.onText(String(body.text), true);
                else latest.current.onError(body.detail || "Couldn't understand that. Please try again or type your message.");
            } catch {
                latest.current.onError("Couldn't send your voice message. Please type it instead.");
            } finally {
                setBusy(false);
            }
        };
        recorder.current = rec;
        setListening(true);
        rec.start();
        timer.current = setTimeout(() => { if (rec.state === "recording") rec.stop(); }, MAX_RECORDING_MS);
    }, [apiBase, botId, headers]);

    const start = useCallback(() => {
        if (listening || busy) return;
        const Cls = recognitionClass();
        if (Cls) startRecognition(Cls); else startRecording();
    }, [listening, busy, startRecognition, startRecording]);

    useEffect(() => () => { recognition.current?.abort(); if (recorder.current?.state === "recording") recorder.current.stop(); }, []);

    return { supported, listening, busy, start, stop };
}
