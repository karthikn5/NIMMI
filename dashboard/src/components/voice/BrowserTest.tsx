"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Mic, MicOff, PhoneOff } from "lucide-react";
import { Button, Card, cn } from "@/components/ui";
import { apiJson, wsUrl } from "@/lib/api";
import { OUTCOMES } from "@/lib/voice/api";
import type { AgentDirection, CallOutcome, VoiceAgentConfig } from "@/lib/voice/types";

type Phase = "idle" | "connecting" | "live" | "ended" | "error";
type Line = { speaker: "agent" | "caller"; text: string };

const BARS = 32;
const TARGET_RATE = 16000;

// Runs on the audio thread: forwards raw mic samples to the main thread.
const WORKLET = `
class Tap extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor("nimmi-tap", Tap);
`;

/** Float32 at the context rate -> Int16 PCM at 16 kHz. */
function downsample(input: Float32Array, fromRate: number): Int16Array {
    const ratio = fromRate / TARGET_RATE;
    const out = new Int16Array(Math.floor(input.length / ratio));
    for (let i = 0; i < out.length; i++) {
        const start = Math.floor(i * ratio);
        const end = Math.min(Math.floor((i + 1) * ratio), input.length);
        let sum = 0;
        for (let j = start; j < end; j++) sum += input[j];
        const v = Math.max(-1, Math.min(1, sum / Math.max(1, end - start)));
        out[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
    }
    return out;
}

export default function BrowserTest({ config, dirty, direction = "inbound" }: { config: VoiceAgentConfig; dirty?: boolean; direction?: AgentDirection }) {
    const [phase, setPhase] = useState<Phase>("idle");
    const [muted, setMuted] = useState(false);
    const [speaking, setSpeaking] = useState(false);
    const [levels, setLevels] = useState<number[]>(() => Array(BARS).fill(0));
    const [lines, setLines] = useState<Line[]>([]);
    const [seconds, setSeconds] = useState(0);
    const [message, setMessage] = useState<string | null>(null);
    const [result, setResult] = useState<{ outcome: CallOutcome; summary: string; callId: string } | null>(null);

    const ws = useRef<WebSocket | null>(null);
    const stream = useRef<MediaStream | null>(null);
    const ctx = useRef<AudioContext | null>(null);
    const frame = useRef(0);
    const playAt = useRef(0);
    const playing = useRef<Set<AudioBufferSourceNode>>(new Set());
    const pending = useRef<Int16Array[]>([]);
    const transcriptEnd = useRef<HTMLDivElement>(null);

    const stopAudio = () => {
        cancelAnimationFrame(frame.current);
        playing.current.forEach((s) => { try { s.stop(); } catch { /* already stopped */ } });
        playing.current.clear();
        pending.current = [];
        stream.current?.getTracks().forEach((t) => t.stop());
        stream.current = null;
        ctx.current?.close().catch(() => {});
        ctx.current = null;
        setSpeaking(false);
    };

    const teardown = () => {
        if (ws.current && ws.current.readyState === WebSocket.OPEN) {
            ws.current.send(JSON.stringify({ type: "hangup" }));
            ws.current.close();
        }
        ws.current = null;
        pending.current = [];
        stopAudio();
    };

    useEffect(() => teardown, []);

    useEffect(() => {
        if (phase !== "live") return;
        const t = setInterval(() => setSeconds((s) => s + 1), 1000);
        return () => clearInterval(t);
    }, [phase]);

    useEffect(() => { transcriptEnd.current?.scrollIntoView({ block: "nearest" }); }, [lines]);

    const clearPlayback = () => {
        playing.current.forEach((s) => { try { s.stop(); } catch { /* noop */ } });
        playing.current.clear();
        if (ctx.current) playAt.current = ctx.current.currentTime;
        setSpeaking(false);
    };

    const playPcm = (buf: ArrayBuffer) => {
        const ac = ctx.current;
        if (!ac) return;
        const pcm = new Int16Array(buf);
        const audio = ac.createBuffer(1, pcm.length, TARGET_RATE);
        const data = audio.getChannelData(0);
        for (let i = 0; i < pcm.length; i++) data[i] = pcm[i] / 0x8000;
        const src = ac.createBufferSource();
        src.buffer = audio;
        src.connect(ac.destination);
        const at = Math.max(ac.currentTime + 0.02, playAt.current);
        src.start(at);
        playAt.current = at + audio.duration;
        playing.current.add(src);
        setSpeaking(true);
        src.onended = () => {
            playing.current.delete(src);
            if (playing.current.size === 0) setSpeaking(false);
        };
    };

    const onEvent = (data: { type: string; text?: string; code?: string; message?: string; outcome?: CallOutcome; summary?: string; call_id?: string }) => {
        if (data.type === "agent" || data.type === "caller") {
            setLines((l) => [...l, { speaker: data.type as Line["speaker"], text: data.text || "" }]);
        } else if (data.type === "clear") {
            clearPlayback();
        } else if (data.type === "error") {
            setMessage(data.code === "no_minutes"
                ? "You're out of voice minutes. Buy minutes from the Voice overview to keep testing."
                : data.message || "The voice engine had a problem.");
        } else if (data.type === "ended") {
            setResult({ outcome: data.outcome || "answered", summary: data.summary || "", callId: data.call_id || "" });
        }
    };

    const start = async () => {
        setPhase("connecting");
        setLines([]);
        setSeconds(0);
        setMuted(false);
        setMessage(null);
        setResult(null);
        pending.current = [];

        let session: { ws_path: string; token: string };
        try {
            session = await apiJson("/api/voice/session", { method: "POST", json: { bot_id: config.bot_id, direction } });
        } catch (e) {
            setMessage((e as Error).message);
            setPhase("error");
            return;
        }

        try {
            stream.current = await navigator.mediaDevices.getUserMedia({
                audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
            });
        } catch {
            setMessage("Microphone access is blocked. Allow it from the lock icon in your address bar, then try again.");
            setPhase("error");
            return;
        }

        const ac = new AudioContext();
        ctx.current = ac;
        playAt.current = ac.currentTime;
        const source = ac.createMediaStreamSource(stream.current);

        // Level meter
        const analyser = ac.createAnalyser();
        analyser.fftSize = 512;
        source.connect(analyser);
        const buf = new Uint8Array(analyser.fftSize);
        let last = 0;
        const tick = (now: number) => {
            if (now - last > 60) {
                analyser.getByteTimeDomainData(buf);
                let sum = 0;
                for (const v of buf) sum += ((v - 128) / 128) ** 2;
                setLevels((prev) => [...prev.slice(1), Math.min(Math.sqrt(sum / buf.length) * 4, 1)]);
                last = now;
            }
            frame.current = requestAnimationFrame(tick);
        };
        frame.current = requestAnimationFrame(tick);

        // Mic capture -> 16 kHz PCM -> WebSocket, in ~100 ms chunks
        const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
        await ac.audioWorklet.addModule(url);
        URL.revokeObjectURL(url);
        const tap = new AudioWorkletNode(ac, "nimmi-tap");
        source.connect(tap);
        let queued = 0;
        tap.port.onmessage = (e: MessageEvent<Float32Array>) => {
            if (!e.data || e.data.length === 0) return;
            const pcm = downsample(e.data, ac.sampleRate);
            if (!pcm || pcm.length === 0) return;
            pending.current.push(pcm);
            queued += pcm.length;
            if (queued >= 1600 && ws.current?.readyState === WebSocket.OPEN) {
                const chunks = pending.current;
                pending.current = [];
                queued = 0;
                const total = chunks.reduce((acc, c) => acc + c.length, 0);
                if (total > 0) {
                    const out = new Int16Array(total);
                    let off = 0;
                    for (const p of chunks) {
                        out.set(p, off);
                        off += p.length;
                    }
                    ws.current.send(out.buffer);
                }
            }
        };

        const socket = new WebSocket(`${wsUrl(session.ws_path)}?token=${encodeURIComponent(session.token)}`);
        socket.binaryType = "arraybuffer";
        ws.current = socket;
        socket.onopen = () => setPhase("live");
        socket.onmessage = (e) => {
            if (typeof e.data === "string") onEvent(JSON.parse(e.data));
            else playPcm(e.data as ArrayBuffer);
        };
        socket.onclose = () => {
            ws.current = null;
            // Let the goodbye finish playing before tearing down audio.
            const ac2 = ctx.current;
            const wait = ac2 ? Math.max(0, (playAt.current - ac2.currentTime) * 1000) : 0;
            setTimeout(stopAudio, wait + 200);
            setPhase((p) => (p === "error" ? p : "ended"));
        };
        socket.onerror = () => {
            setMessage("Lost the connection to the voice engine.");
            setPhase("error");
        };
    };

    const end = () => {
        teardown();
        setPhase("ended");
    };

    const toggleMute = () => {
        const next = !muted;
        stream.current?.getAudioTracks().forEach((t) => { t.enabled = !next; });
        setMuted(next);
    };

    const live = phase === "live";
    const clock = `${Math.floor(seconds / 60)}:${(seconds % 60).toString().padStart(2, "0")}`;

    return (
        <Card className="overflow-hidden">
            <div className="px-5 pt-5">
                <h2 className="text-[15px] font-semibold">Try it</h2>
                <p className="text-[13px] text-stone-500 mt-0.5">
                    Talk to {config.bot_name} through your microphone. Test calls use your saved settings and count toward your minutes.
                </p>
                {dirty && <p className="text-[13px] text-amber-700 mt-2">Save your changes to hear them in a test call.</p>}
            </div>

            <div className="px-5 py-5">
                <div className={cn("flex items-center gap-[3px] h-12 px-3 rounded-md bg-stone-50 border border-line", !live && "opacity-60")} aria-hidden>
                    {levels.map((v, i) => (
                        <span key={i} className={cn("flex-1 rounded-full transition-[height] duration-75", muted ? "bg-stone-300" : "bg-plum-data")}
                              style={{ height: `${Math.max(v * 100, 6)}%` }} />
                    ))}
                </div>

                {live ? (
                    <div className="flex items-center gap-2 mt-3">
                        <span className="inline-flex items-center gap-1.5 text-[13px] text-stone-700 tabular-nums mr-auto">
                            <span className="h-1.5 w-1.5 rounded-full bg-signal" aria-hidden />
                            {muted ? "Muted" : speaking ? `${config.assistant_name} is speaking` : "Listening"} · {clock}
                        </span>
                        <Button size="sm" variant="ghost" onClick={toggleMute} aria-pressed={muted}>
                            {muted ? <MicOff size={14} /> : <Mic size={14} />} {muted ? "Unmute" : "Mute"}
                        </Button>
                        <Button size="sm" variant="danger" onClick={end}><PhoneOff size={14} /> End</Button>
                    </div>
                ) : (
                    <Button variant="primary" className="w-full mt-3" onClick={start} disabled={phase === "connecting"}>
                        <Mic size={15} /> {phase === "connecting" ? "Connecting…" : phase === "ended" ? "Call again" : "Start test call"}
                    </Button>
                )}

                {message && <p className="text-[13px] text-signal mt-3">{message}</p>}
            </div>

            {(lines.length > 0 || live) && (
                <div className="border-t border-line">
                    <div className="max-h-72 overflow-y-auto px-5 py-3 space-y-3" aria-live="polite">
                        {lines.length === 0 && <p className="text-[13px] text-stone-400">Connecting…</p>}
                        {lines.map((l, i) => (
                            <div key={i} className="text-[13px] leading-relaxed">
                                <span className={cn("block text-xs mb-0.5", l.speaker === "agent" ? "text-plum font-medium" : "text-stone-500")}>
                                    {l.speaker === "agent" ? config.assistant_name || "Assistant" : "You"}
                                </span>
                                <span className="text-stone-800">{l.text}</span>
                            </div>
                        ))}
                        <div ref={transcriptEnd} />
                    </div>
                </div>
            )}

            {result && (
                <div className="border-t border-line px-5 py-4 text-[13px]">
                    <p><span className="text-stone-500">Outcome:</span> {OUTCOMES[result.outcome]?.label ?? result.outcome}</p>
                    {result.summary && <p className="text-stone-700 mt-1">{result.summary}</p>}
                    {result.callId && (
                        <Link href={`/dashboard/voice/calls?call=${result.callId}`} className="inline-block mt-2 text-plum hover:underline underline-offset-4">
                            Open the call log
                        </Link>
                    )}
                </div>
            )}
        </Card>
    );
}
