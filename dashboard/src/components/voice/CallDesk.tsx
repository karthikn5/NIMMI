"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Bell, ChevronDown, Headset, Mic, MicOff, Phone, PhoneOff, Volume2, VolumeX, X } from "lucide-react";
import type { Call, Device } from "@twilio/voice-sdk";
import { Button, Input, cn } from "@/components/ui";
import {
    acceptCall, browserToken, declineCall, formatClock, refreshLive, setAvailability, useLive,
    type CallRequest, type LiveLine,
} from "@/lib/voice/live";

/**
 * The call desk, on every dashboard page (LIVE_CALLS_PLAN.md). A caller who needs a person rings here: a card with who,
 * why, how long they've waited and what was said, a ring, and a desktop notification when the tab is in the
 * background. "Pick up here" takes the call in this browser (Twilio numbers), "Call my phone" rings the person's phone,
 * "Let the assistant handle it" lets it go. Picked up in the browser, a call bar: the caller, the time, mute, hang up.
 * The Calls page uses the same actions, and the ring's settings (useCallDesk).
 */
type OnCall = { device: Device; call: Call; request: CallRequest; since: number; muted: boolean };
type Desk = {
    pickUp: (request: CallRequest, via: "browser" | "phone") => Promise<void>;
    letGo: (request: CallRequest) => Promise<void>;
    busy: string | null;
    onCall: OnCall | null;
    sound: boolean;
    setSound: (on: boolean) => void;
    testRing: () => void;
    soundBlocked: boolean;  // the ring is on, but the browser won't play it until the page is clicked
};

const DeskContext = createContext<Desk | null>(null);
export const useCallDesk = () => useContext(DeskContext);
export const SOUND_HINT = "Your browser plays the ring only after you click on this page. Click anywhere to allow it.";

/**
 * The ring: India's double ring (0.4 s on, 0.2 s off, 0.4 s on, 2 s off), a two-note chord whose level wobbles 25 times
 * a second like a phone's bell, loud enough to hear across a room (measured in Chrome: peaks at -5.5 dBFS, -15 dBFS RMS
 * while ringing; it can't pass -4.5 dBFS, so it never clips). Made here (no sound file) and scheduled on the audio
 * clock, so it keeps its rhythm in a background tab, where the browser slows timers.
 */
const RING_ON = 0.4;
const RING_GAP = 0.2;
const RING_CYCLE = 3.0;
const RING_VOLUME = 0.22;
const RING_LOCK = "nimmi-call-ring";
const SOUND_KEY = "nimmi_call_sound";

/** Ring for `seconds` from now; returns what silences it. */
function ringFor(ctx: AudioContext, seconds: number): () => void {
    const at = ctx.currentTime + 0.05;
    const end = at + seconds;
    const shape = ctx.createGain();  // the rhythm: each ring rises in 15 ms and falls in 40 ms, so it never clicks
    shape.gain.value = 0;
    for (let t = at; t < end; t += RING_CYCLE) {
        for (const on of [t, t + RING_ON + RING_GAP]) {
            shape.gain.setValueAtTime(0, on);
            shape.gain.linearRampToValueAtTime(1, on + 0.015);
            shape.gain.setValueAtTime(1, on + RING_ON - 0.04);
            shape.gain.linearRampToValueAtTime(0, on + RING_ON);
        }
    }
    const tremolo = ctx.createGain();  // 0.7 +- 0.3
    tremolo.gain.value = 0.7;
    const lfo = ctx.createOscillator();
    lfo.frequency.value = 25;
    const depth = ctx.createGain();
    depth.gain.value = 0.3;
    lfo.connect(depth).connect(tremolo.gain);
    const out = ctx.createGain();
    out.gain.value = RING_VOLUME;
    tremolo.connect(shape).connect(out).connect(ctx.destination);
    // A and C sharp (a major third), each with a softer octave above it so it carries on laptop speakers.
    const tones = [[440, 1], [554.37, 1], [880, 0.35], [1108.73, 0.35]].map(([freq, level]) => {
        const osc = ctx.createOscillator();
        osc.frequency.value = freq;
        const gain = ctx.createGain();
        gain.gain.value = level;
        osc.connect(gain).connect(tremolo);
        return osc;
    });
    const sources = [lfo, ...tones];
    sources.forEach((s) => { s.start(at); s.stop(end + RING_CYCLE); });
    return () => {
        const now = ctx.currentTime;
        out.gain.cancelScheduledValues(now);
        out.gain.setTargetAtTime(0, now, 0.015);
        sources.forEach((s) => { try { s.stop(now + 0.1); } catch { /* already stopped */ } });
    };
}

/** Resolves once the browser lets this page play sound (at once if it already does). */
function soundAllowed(ctx: AudioContext, signal: AbortSignal): Promise<void> {
    return new Promise((resolve) => {
        const check = () => {
            if (ctx.state !== "running") return;
            ctx.removeEventListener("statechange", check);
            resolve();
        };
        ctx.addEventListener("statechange", check);
        signal.addEventListener("abort", () => ctx.removeEventListener("statechange", check));
        check();
    });
}

function soundStored(): boolean {
    try { return localStorage.getItem(SOUND_KEY) !== "off"; } catch { return true; }
}

/** The call Twilio rings this browser with, once the caller is handed over (or an error after `ms`). */
function incomingCall(device: Device, handoffId: string, ms: number): Promise<Call> {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("The call didn't come through. The caller will get a call back.")), ms);
        device.on("incoming", (call: Call) => {
            if (call.customParameters.get("handoff") === handoffId) {
                clearTimeout(timer);
                resolve(call);
            } else {
                call.reject();
            }
        });
    });
}

export default function CallDeskProvider({ children }: { children: ReactNode }) {
    const live = useLive();
    const [busy, setBusy] = useState<string | null>(null);
    const [onCall, setOnCall] = useState<OnCall | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [askPhone, setAskPhone] = useState<CallRequest | null>(null);
    const [note, setNote] = useState<string | null>(null);

    const pickUp = useCallback(async (request: CallRequest, via: "browser" | "phone", phone?: string) => {
        setBusy(request.id);
        setError(null);
        setNote(null);
        let device: Device | null = null;
        try {
            if (request.test) {  // a test call in the browser has no phone line: the assistant explains instead
                const r = await acceptCall(request.id, "browser");
                if (!r.ok) throw new Error(r.message);
                setNote("Picked up. This is a test call, so the assistant explains that on a phone call you'd be talking now.");
                return;
            }
            if (via === "phone") {
                if (!phone && !live.me.phone) { setAskPhone(request); return; }
                const r = await acceptCall(request.id, "phone", phone);
                if (!r.ok) throw new Error(r.message);
                setAskPhone(null);
                setNote("Your phone will ring in a moment. Answer it to talk to the caller.");
                return;
            }
            // The microphone first (the click allows asking), so the call doesn't stall on the browser's prompt.
            const mic = await navigator.mediaDevices.getUserMedia({ audio: true }).catch(() => null);
            if (!mic) throw new Error("Allow the microphone for this site to take calls here, or use Call my phone.");
            mic.getTracks().forEach((t) => t.stop());
            const token = await browserToken(request.id);
            if (!token.ok || !token.data) throw new Error(token.message);
            const { Device: TwilioDevice, Call: TwilioCall } = await import("@twilio/voice-sdk");
            const ready = new TwilioDevice(String(token.data.token), {
                edge: token.data.edge as string[],
                closeProtection: "You're on a call. Leave anyway?",
                codecPreferences: [TwilioCall.Codec.Opus, TwilioCall.Codec.PCMU],
                logLevel: "error",
            });
            device = ready;
            await new Promise<void>((resolve, reject) => {
                const timer = setTimeout(() => reject(new Error("This browser couldn't get ready for calls. Use Call my phone.")), 12000);
                ready.once("registered", () => { clearTimeout(timer); resolve(); });
                ready.once("error", (e: { message?: string }) => { clearTimeout(timer); reject(new Error(e?.message || "This browser couldn't get ready for calls.")); });
                void ready.register();
            });
            const coming = incomingCall(ready, request.id, 30000);
            const r = await acceptCall(request.id, "browser");
            if (!r.ok) throw new Error(r.message);
            const call = await coming;  // the assistant says it's connecting them, then Twilio rings this browser
            call.accept();
            const done = () => { ready.destroy(); setOnCall(null); void refreshLive(); };
            call.on("disconnect", done);
            call.on("cancel", done);
            call.on("error", () => setError("The call had a problem. If it dropped, the caller will be called back."));
            setOnCall({ device: ready, call, request, since: Date.now(), muted: false });
            device = null;  // the call owns it now
        } catch (e) {
            setError((e as Error).message || "That didn't work.");
        } finally {
            device?.destroy();
            setBusy(null);
        }
    }, [live.me.phone]);

    const letGo = useCallback(async (request: CallRequest) => {
        const r = await declineCall(request.id);
        if (!r.ok) setError(r.message);
    }, []);

    // Ring while a caller waits for this person (available, not on a call already).
    const waiting = useMemo(() => live.me.available && !onCall ? live.requests.filter((r) => !r.mine) : [],
                            [live.me.available, live.requests, onCall]);
    const [sound, setSoundState] = useState(true);
    useEffect(() => setSoundState(soundStored()), []);
    const setSound = useCallback((on: boolean) => {
        setSoundState(on);
        try { localStorage.setItem(SOUND_KEY, on ? "on" : "off"); } catch { /* not remembered: fine */ }
    }, []);
    const audio = useRef<AudioContext | null>(null);
    const [audioState, setAudioState] = useState<AudioContextState | null>(null);
    const context = useCallback((): AudioContext | null => {
        try {
            if (!audio.current) {
                const ctx = new AudioContext();
                ctx.addEventListener("statechange", () => setAudioState(ctx.state));
                setAudioState(ctx.state);
                audio.current = ctx;
            }
            if (audio.current.state === "suspended") void audio.current.resume().catch(() => {});
            return audio.current;
        } catch {
            return null;
        }
    }, []);
    // Browsers play sound only once the person has clicked or typed on the page: wake the audio up at the first one, so
    // a caller can ring later without a click.
    useEffect(() => {
        const kinds = ["pointerdown", "pointerup", "keydown", "touchend"];
        const unlock = () => {
            if (context()?.state === "running") kinds.forEach((k) => window.removeEventListener(k, unlock));
        };
        kinds.forEach((k) => window.addEventListener(k, unlock, { passive: true }));
        return () => kinds.forEach((k) => window.removeEventListener(k, unlock));
    }, [context]);
    const ringing = waiting.map((r) => r.id).join(",");
    useEffect(() => {
        if (!ringing || !sound) return;
        const ctx = context();
        if (!ctx) return;
        const done = new AbortController();
        let silence = () => {};
        const ring = () => new Promise<void>((resolve) => {
            if (done.signal.aborted) return resolve();
            silence = ringFor(ctx, 120);  // a caller waits two minutes at most (the agent's longest wait)
            done.signal.addEventListener("abort", () => resolve());
        });
        // One ring per computer: with several dashboard tabs open, one rings and the others wait, taking over if it's
        // closed. A tab the browser doesn't let play sound yet waits until it does, so it never rings in silence.
        void soundAllowed(ctx, done.signal)
            .then(async () => { await (navigator.locks ? navigator.locks.request(RING_LOCK, { signal: done.signal }, ring) : ring()); })
            .catch(() => { /* answered, or the caller stopped waiting */ });
        return () => { done.abort(); silence(); };
    }, [ringing, sound, context]);
    const testRing = useCallback(() => {
        const ctx = context();
        if (ctx) ringFor(ctx, 1);
    }, [context]);
    const soundBlocked = sound && audioState !== null && audioState !== "running";

    // The tab's title says a caller is waiting (it shows among many tabs); a desktop notification for each new caller
    // when this tab isn't the one in front, kept until they're answered and closed once nobody waits for it.
    useEffect(() => {
        if (!waiting.length) return;
        const flash = `(${waiting.length}) Caller waiting`;
        let original = document.title;
        const timer = setInterval(() => {
            if (document.title !== flash) original = document.title;  // the page may have changed it meanwhile
            document.title = document.title === flash ? original : flash;
        }, 1000);
        return () => {
            clearInterval(timer);
            if (document.title === flash) document.title = original;
        };
    }, [waiting.length]);
    const notes = useRef(new Map<string, Notification>());
    useEffect(() => {
        const ids = new Set(waiting.map((r) => r.id));
        for (const [id, n] of notes.current) {
            if (!ids.has(id)) { n.close(); notes.current.delete(id); }
        }
        if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
        for (const r of waiting) {
            if (notes.current.has(r.id) || (!document.hidden && document.hasFocus())) continue;
            const n = new Notification("A caller wants a person", {
                body: `${r.caller_name || r.caller} on ${r.bot_name}: ${r.reason}`, tag: r.id, requireInteraction: true, silent: !sound,
            });
            n.onclick = () => { window.focus(); n.close(); };
            notes.current.set(r.id, n);
        }
    }, [waiting, sound]);

    const desk = useMemo<Desk>(() => ({ pickUp: (r, via) => pickUp(r, via), letGo, busy, onCall, sound, setSound, testRing, soundBlocked }),
                               [pickUp, letGo, busy, onCall, sound, setSound, testRing, soundBlocked]);
    return (
        <DeskContext.Provider value={desk}>
            {children}
            <div className="fixed bottom-4 left-4 z-[60] w-[min(380px,calc(100vw-2rem))] space-y-2" aria-live="polite">
                {onCall && <CallBar onCall={onCall} setOnCall={setOnCall} />}
                {!onCall && waiting[0] && (
                    <RequestCard request={waiting[0]} more={waiting.length - 1} at={live.at} busy={busy === waiting[0].id}
                                 onPickUp={(via) => void pickUp(waiting[0], via)} onLetGo={() => void letGo(waiting[0])}
                                 onUnavailable={() => void setAvailability({ available: false })}
                                 sound={sound} blocked={soundBlocked} onSound={() => setSound(!sound)} />
                )}
                {askPhone && (
                    <PhoneAsk request={askPhone} busy={busy === askPhone.id} onCancel={() => setAskPhone(null)}
                              onRing={(phone) => void pickUp(askPhone, "phone", phone)} />
                )}
                {(error || note) && (
                    <p role={error ? "alert" : "status"} className={cn("flex items-start gap-2 rounded-lg border px-3 py-2 text-[13px] shadow-sm",
                        error ? "border-signal/30 bg-white text-signal" : "border-line bg-white text-stone-700")}>
                        <span className="flex-1">{error || note}</span>
                        <button type="button" aria-label="Close" onClick={() => { setError(null); setNote(null); }} className="text-stone-400 hover:text-ink"><X size={14} /></button>
                    </p>
                )}
            </div>
        </DeskContext.Provider>
    );
}

function useTick(): number {
    const [, setNow] = useState(0);
    useEffect(() => {
        const timer = setInterval(() => setNow((n) => n + 1), 1000);
        return () => clearInterval(timer);
    }, []);
    return Date.now();
}

function Lines({ lines }: { lines: LiveLine[] }) {
    return (
        <ol className="space-y-1.5">
            {lines.map((l, i) => (
                <li key={i} className="text-[12.5px] leading-snug">
                    <span className={cn("font-medium", l.speaker === "agent" ? "text-plum" : "text-stone-600")}>
                        {l.speaker === "agent" ? "Assistant" : "Caller"}:
                    </span>{" "}
                    <span className="text-stone-700">{l.text}</span>
                </li>
            ))}
        </ol>
    );
}

function RequestCard({ request, more, at, busy, onPickUp, onLetGo, onUnavailable, sound, blocked, onSound }: {
    request: CallRequest; more: number; at: number; busy: boolean;
    onPickUp: (via: "browser" | "phone") => void; onLetGo: () => void; onUnavailable: () => void;
    sound: boolean; blocked: boolean; onSound: () => void;
}) {
    const now = useTick();
    const [open, setOpen] = useState(false);
    const passed = Math.floor((now - at) / 1000);
    const permission = typeof Notification === "undefined" ? "denied" : Notification.permission;
    return (
        <section aria-label="A caller wants a person" className="rounded-xl border border-plum/30 bg-white shadow-[0_16px_40px_rgba(28,23,25,0.18)]">
            <header className="flex items-center gap-2.5 px-4 pt-3.5">
                <span className="relative flex h-8 w-8 items-center justify-center rounded-full bg-plum-tint text-plum">
                    <span className="absolute inset-0 rounded-full bg-plum/20 animate-ping" aria-hidden />
                    <Headset size={16} aria-hidden />
                </span>
                <div className="min-w-0 flex-1">
                    <p className="text-[13.5px] font-semibold leading-tight">{request.test ? "Test call: " : ""}A caller wants a person</p>
                    <p className="text-[12px] text-stone-500 tabular-nums">
                        Waiting {formatClock(request.waited_sec + passed)} · {request.bot_name}{more > 0 ? ` · ${more} more waiting` : ""}
                    </p>
                </div>
            </header>
            <div className="px-4 pt-2.5 pb-3 space-y-2">
                <p className="text-[13px]">
                    <span className="font-medium tabular-nums">{request.caller_name || request.caller}</span>
                    {request.caller_name && <span className="text-stone-500 tabular-nums"> · {request.caller}</span>}
                </p>
                <p className="text-[13px] text-stone-700">{request.reason}</p>
                {request.lines.length > 0 && (
                    <div>
                        <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
                                className="inline-flex items-center gap-1 text-[12px] font-medium text-stone-500 hover:text-ink">
                            <ChevronDown size={13} className={cn("transition-transform", open && "rotate-180")} aria-hidden /> What was said
                        </button>
                        {open && <div className="mt-1.5 max-h-40 overflow-y-auto rounded-md bg-stone-50 px-2.5 py-2"><Lines lines={request.lines} /></div>}
                    </div>
                )}
                <div className="flex flex-wrap gap-2 pt-1">
                    {request.browser && (
                        <Button size="sm" variant="primary" disabled={busy} onClick={() => onPickUp("browser")}>
                            <Headset size={14} aria-hidden /> {busy ? "Connecting…" : "Pick up here"}
                        </Button>
                    )}
                    {request.phone && (
                        <Button size="sm" variant={request.browser ? "secondary" : "primary"} disabled={busy} onClick={() => onPickUp("phone")}>
                            <Phone size={14} aria-hidden /> Call my phone
                        </Button>
                    )}
                    {request.test && !request.browser && !request.phone && (
                        <Button size="sm" variant="primary" disabled={busy} onClick={() => onPickUp("browser")}>Pick up (test)</Button>
                    )}
                    <Button size="sm" variant="ghost" disabled={busy} onClick={onLetGo}>Let the assistant handle it</Button>
                </div>
                {blocked && <p className="text-[12px] text-plum">{SOUND_HINT}</p>}
            </div>
            <footer className="flex items-center gap-3 border-t border-line px-4 py-2 text-[11.5px] text-stone-500">
                <button type="button" onClick={onSound} aria-pressed={sound} className="inline-flex items-center gap-1 hover:text-ink">
                    {sound ? <Volume2 size={12} aria-hidden /> : <VolumeX size={12} aria-hidden />} {sound ? "Sound on" : "Sound off"}
                </button>
                {permission === "default" && (
                    <button type="button" onClick={() => void Notification.requestPermission()} className="inline-flex items-center gap-1 hover:text-ink">
                        <Bell size={12} aria-hidden /> Desktop alerts
                    </button>
                )}
                <button type="button" onClick={onUnavailable} className="ml-auto hover:text-ink">I'm not taking calls now</button>
            </footer>
        </section>
    );
}

function PhoneAsk({ request, busy, onRing, onCancel }: {
    request: CallRequest; busy: boolean; onRing: (phone: string) => void; onCancel: () => void;
}) {
    const [phone, setPhone] = useState("");
    return (
        <form onSubmit={(e) => { e.preventDefault(); if (phone.trim()) onRing(phone.trim()); }}
              className="rounded-xl border border-line bg-white px-4 py-3 shadow-[0_12px_32px_rgba(28,23,25,0.14)]">
            <label htmlFor="desk-phone" className="text-[13px] font-medium">Your phone number</label>
            <p className="text-[12px] text-stone-500">We ring it to connect you to {request.caller_name || "the caller"}. It's kept for next time.</p>
            <div className="mt-2 flex gap-2">
                <Input id="desk-phone" type="tel" inputMode="tel" autoFocus placeholder="98400 12345" value={phone}
                       onChange={(e) => setPhone(e.target.value)} className="tabular-nums" />
                <Button size="sm" variant="primary" type="submit" disabled={busy || !phone.trim()}>Ring me</Button>
                <Button size="sm" variant="ghost" type="button" onClick={onCancel}>Cancel</Button>
            </div>
        </form>
    );
}

function CallBar({ onCall, setOnCall }: { onCall: OnCall; setOnCall: (c: OnCall | null) => void }) {
    const now = useTick();
    const [open, setOpen] = useState(false);
    const { call, request } = onCall;
    const mute = () => {
        call.mute(!onCall.muted);
        setOnCall({ ...onCall, muted: !onCall.muted });
    };
    return (
        <section aria-label="On a call" className="rounded-xl border border-emerald-600/30 bg-white shadow-[0_16px_40px_rgba(28,23,25,0.18)]">
            <div className="flex items-center gap-3 px-4 py-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-50 text-emerald-700"><Phone size={15} aria-hidden /></span>
                <div className="min-w-0 flex-1">
                    <p className="text-[13.5px] font-semibold leading-tight">On a call · <span className="tabular-nums">{formatClock(Math.floor((now - onCall.since) / 1000))}</span></p>
                    <p className="truncate text-[12px] text-stone-500 tabular-nums">{request.caller_name || request.caller} · {request.bot_name}</p>
                </div>
                <button type="button" onClick={mute} aria-pressed={onCall.muted} aria-label={onCall.muted ? "Unmute" : "Mute"}
                        className={cn("h-9 w-9 rounded-full flex items-center justify-center border", onCall.muted ? "border-plum bg-plum-tint text-plum" : "border-line text-stone-600 hover:bg-stone-50")}>
                    {onCall.muted ? <MicOff size={15} /> : <Mic size={15} />}
                </button>
                <button type="button" onClick={() => call.disconnect()} aria-label="Hang up"
                        className="h-9 w-9 rounded-full flex items-center justify-center bg-signal text-white hover:opacity-90">
                    <PhoneOff size={15} />
                </button>
            </div>
            <div className="border-t border-line px-4 py-2">
                <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
                        className="inline-flex items-center gap-1 text-[12px] font-medium text-stone-500 hover:text-ink">
                    <ChevronDown size={13} className={cn("transition-transform", open && "rotate-180")} aria-hidden /> Why they called
                </button>
                {open && (
                    <div className="mt-1.5 space-y-2 pb-1">
                        <p className="text-[12.5px] text-stone-700">{request.reason}</p>
                        <Lines lines={request.lines} />
                    </div>
                )}
            </div>
        </section>
    );
}
