"use client";

import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState, type KeyboardEvent } from "react";
import {
    ArrowUp, ChartColumn, Check, Eye, History, Keyboard, Loader2, MessageCircle, Mic, Phone, Plus, Slash, Sparkles,
    Square, WandSparkles, X, type LucideIcon,
} from "lucide-react";
import { cn } from "@/components/ui";
import { useRecorder } from "@/lib/agent/useRecorder";

/**
 * Where the person writes to Nimmi: the message box, the mic (speak instead of typing: the words land in the box to
 * check), and "/" shortcuts for the common things. Enter sends; Shift + Enter makes a new line.
 */
export type ComposerAction = "changes" | "new" | "shortcuts";
type Command = { key: string; label: string; hint: string; icon: LucideIcon; send?: string; fill?: string; action?: ComposerAction };

export const COMMANDS: Command[] = [
    { key: "explain", label: "Explain this page", hint: "What it's for, and what to do here", icon: Eye, send: "What can I do on this page?" },
    { key: "change", label: "Make a change", hint: "Colours, knowledge, instructions, voice…", icon: WandSparkles, fill: "Change " },
    { key: "create", label: "Build an assistant", hint: "From your website, step by step", icon: Sparkles, send: "Create a new assistant from my website." },
    { key: "whatsapp", label: "Connect WhatsApp", hint: "The steps, then Nimmi's form", icon: MessageCircle, send: "How do I connect my WhatsApp number?" },
    { key: "phone", label: "Connect a phone number", hint: "Your own Twilio or Exotel number", icon: Phone, send: "How do I connect my own phone number?" },
    { key: "report", label: "How am I doing?", hint: "Chats, leads and calls this month", icon: ChartColumn, send: "How did this month compare with last month?" },
    { key: "changes", label: "What Nimmi changed", hint: "Every change, with Undo", icon: History, action: "changes" },
    { key: "new", label: "New chat", hint: "Start fresh", icon: Plus, action: "new" },
    { key: "shortcuts", label: "Keyboard shortcuts", hint: "", icon: Keyboard, action: "shortcuts" },
];
const LIMIT = 4000;

export type ComposerHandle = { focus: () => void; fill: (text: string) => void };

type Props = {
    running: boolean;
    disabled: boolean;
    onSend: (text: string) => void;
    onStop: () => void;
    onAction: (action: ComposerAction) => void;
    onError: (message: string) => void;
    onListening: (on: boolean) => void;
};

const AgentComposer = forwardRef<ComposerHandle, Props>(function AgentComposer({ running, disabled, onSend, onStop, onAction, onError, onListening }, ref) {
    const [draft, setDraft] = useState("");
    const [menu, setMenu] = useState(false);
    const [pick, setPick] = useState(0);
    const box = useRef<HTMLTextAreaElement>(null);

    useImperativeHandle(ref, () => ({
        focus: () => box.current?.focus(),
        fill: (text: string) => { setDraft(text); setTimeout(() => { box.current?.focus(); box.current?.setSelectionRange(text.length, text.length); }, 0); },
    }));

    const mic = useRecorder((text) => setDraft((d) => (d.trim() ? `${d.trimEnd()} ${text}` : text)), onError);
    const hearing = mic.state === "recording" || mic.state === "starting";
    useEffect(() => { onListening(hearing); }, [hearing, onListening]);
    // Once their words are written out, the box takes focus (it's disabled while writing), caret at the end: Enter sends.
    const before = useRef(mic.state);
    useEffect(() => {
        if (before.current === "transcribing" && mic.state === "idle" && box.current) {
            const end = box.current.value.length;
            box.current.focus();
            box.current.setSelectionRange(end, end);
        }
        before.current = mic.state;
    }, [mic.state]);

    const query = draft.startsWith("/") ? draft.slice(1).toLowerCase() : "";
    const showMenu = menu || (draft.startsWith("/") && !draft.includes(" "));
    const options = useMemo(() => COMMANDS.filter((c) => !query || c.key.startsWith(query) || c.label.toLowerCase().includes(query)), [query]);

    const run = (c: Command) => {
        setMenu(false);
        setPick(0);
        if (c.action) { setDraft(""); onAction(c.action); return; }
        if (c.fill) { setDraft(c.fill); setTimeout(() => box.current?.focus(), 0); return; }
        if (c.send) { setDraft(""); onSend(c.send); }
    };
    const submit = () => {
        if (!draft.trim() || running || disabled) return;
        onSend(draft);
        setDraft("");
    };
    const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (showMenu && options.length) {
            if (e.key === "ArrowDown") { e.preventDefault(); setPick((p) => (p + 1) % options.length); return; }
            if (e.key === "ArrowUp") { e.preventDefault(); setPick((p) => (p - 1 + options.length) % options.length); return; }
            if ((e.key === "Enter" || e.key === "Tab") && !e.shiftKey) { e.preventDefault(); run(options[Math.min(pick, options.length - 1)]); return; }
            if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setMenu(false); if (draft.startsWith("/")) setDraft(""); return; }
        }
        if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
        }
    };

    const listening = mic.state === "recording" || mic.state === "starting";
    const clock = `${Math.floor(mic.seconds / 60)}:${String(mic.seconds % 60).padStart(2, "0")}`;

    return (
        <div className="relative shrink-0 border-t border-line bg-white p-2.5">
            {showMenu && options.length > 0 && !listening && (
                <div role="listbox" aria-label="Shortcuts"
                     className="absolute left-2.5 right-2.5 bottom-[calc(100%-4px)] z-10 rounded-lg border border-line bg-white shadow-[0_12px_32px_rgba(28,23,25,0.14)] py-1 max-h-72 overflow-y-auto">
                    <p className="px-3 pt-1.5 pb-1 text-[11px] font-medium uppercase tracking-wide text-stone-400">Shortcuts</p>
                    {options.map((c, i) => (
                        <button key={c.key} type="button" role="option" aria-selected={i === pick} onMouseEnter={() => setPick(i)}
                                onMouseDown={(e) => { e.preventDefault(); run(c); }}
                                className={cn("w-full flex items-center gap-2.5 px-3 py-2 text-left", i === pick ? "bg-plum-tint" : "hover:bg-stone-50")}>
                            <span className="h-7 w-7 shrink-0 rounded-md bg-stone-100 text-stone-600 flex items-center justify-center"><c.icon size={14} aria-hidden /></span>
                            <span className="min-w-0 flex-1">
                                <span className="block text-[13px] font-medium text-ink">{c.label}</span>
                                {c.hint && <span className="block text-[11.5px] text-stone-500 truncate">{c.hint}</span>}
                            </span>
                            <span className="text-[11px] font-mono text-stone-400">/{c.key}</span>
                        </button>
                    ))}
                </div>
            )}

            <div className={cn("rounded-xl border bg-white transition-colors", listening ? "border-signal/40" : "border-line-strong focus-within:border-plum")}>
                {listening ? (
                    <div className="flex items-center gap-3 px-3 h-[52px]" aria-live="polite">
                        <span className="relative flex h-2.5 w-2.5" aria-hidden>
                            <span className="absolute inline-flex h-full w-full rounded-full bg-signal opacity-60 animate-ping" />
                            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-signal" />
                        </span>
                        <span className="text-[13px] font-medium">Listening</span>
                        <span className="text-[12px] tabular-nums text-stone-500">{clock}</span>
                        <span className="flex-1 flex items-center justify-center gap-[3px] h-6" aria-hidden>
                            {[0.5, 0.8, 1, 0.75, 0.55, 0.9, 0.65].map((w, i) => (
                                <span key={i} className="w-[3px] rounded-full bg-plum transition-[height] duration-75"
                                      style={{ height: `${Math.max(3, Math.min(22, 3 + mic.level * 26 * w))}px` }} />
                            ))}
                        </span>
                        <button type="button" onClick={() => mic.stop(false)} aria-label="Cancel recording" title="Cancel"
                                className="h-8 w-8 rounded-md flex items-center justify-center text-stone-500 hover:text-ink hover:bg-stone-100">
                            <X size={16} />
                        </button>
                        <button type="button" onClick={() => mic.stop(true)} aria-label="Done speaking" title="Done"
                                className="h-8 w-8 rounded-md bg-plum text-white flex items-center justify-center hover:bg-plum-hover">
                            <Check size={16} />
                        </button>
                    </div>
                ) : (
                    <>
                        <textarea
                            ref={box}
                            value={draft}
                            onChange={(e) => { setDraft(e.target.value.slice(0, LIMIT)); setPick(0); }}
                            onKeyDown={onKey}
                            rows={1}
                            placeholder={mic.state === "transcribing" ? "Writing out what you said…" : "Ask Nimmi, or type / for shortcuts"}
                            aria-label="Message Nimmi"
                            disabled={mic.state === "transcribing"}
                            className="block w-full resize-none bg-transparent px-3 pt-2.5 pb-1 text-[13.5px] leading-6 max-h-40 outline-none [field-sizing:content] disabled:opacity-60"
                        />
                        <div className="flex items-center gap-1 px-1.5 pb-1.5">
                            {mic.supported && (
                                <button type="button" onClick={() => void mic.start()} disabled={running || disabled || mic.state !== "idle"}
                                        aria-label="Speak your message" title="Speak (Indian languages, mixes like Tanglish)"
                                        className="h-8 w-8 rounded-md flex items-center justify-center text-stone-500 hover:text-plum hover:bg-plum-tint disabled:opacity-40">
                                    {mic.state === "transcribing" ? <Loader2 size={16} className="animate-spin" /> : <Mic size={16} />}
                                </button>
                            )}
                            <button type="button" onClick={() => { setMenu((m) => !m); box.current?.focus(); }} aria-label="Shortcuts" aria-expanded={showMenu}
                                    title="Shortcuts ( / )" className={cn("h-8 w-8 rounded-md flex items-center justify-center hover:bg-stone-100",
                                                                          showMenu ? "text-plum bg-plum-tint" : "text-stone-500 hover:text-ink")}>
                                <Slash size={15} />
                            </button>
                            <span className="ml-auto mr-1.5 text-[11px] tabular-nums text-stone-400">
                                {draft.length > LIMIT - 500 ? `${draft.length} / ${LIMIT}` : ""}
                            </span>
                            {running ? (
                                <button type="button" onClick={onStop} aria-label="Stop" title="Stop"
                                        className="h-8 w-8 shrink-0 rounded-md bg-ink text-white flex items-center justify-center hover:bg-stone-700">
                                    <Square size={12} fill="currentColor" />
                                </button>
                            ) : (
                                <button type="button" onClick={submit} disabled={!draft.trim() || disabled} aria-label="Send" title="Send (Enter)"
                                        className="h-8 w-8 shrink-0 rounded-md bg-plum text-white flex items-center justify-center hover:bg-plum-hover disabled:opacity-40">
                                    <ArrowUp size={16} />
                                </button>
                            )}
                        </div>
                    </>
                )}
            </div>
            <p className="mt-1.5 px-1 text-[10.5px] text-stone-400">
                Nimmi can make mistakes; check anything important.<span className="hidden sm:inline"> Changes can be undone.</span>
            </p>
        </div>
    );
});

export default AgentComposer;
