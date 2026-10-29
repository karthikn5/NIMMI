"use client";

import { useState } from "react";
import {
    Check, CircleAlert, Copy, Eye, Loader2, PlugZap, RotateCcw, Sparkles, Square, ThumbsDown, ThumbsUp, Undo2, Volume2,
    WandSparkles,
} from "lucide-react";
import { cn } from "@/components/ui";
import { suggestionsFor } from "@/lib/agent/screens";
import AgentText from "./AgentText";
import AgentCard from "./AgentCards";
import { useAgent, type Item } from "./AgentProvider";

/** The conversation: the person's messages, and Nimmi's turns (her steps, cards and words) beside her avatar. */

export type Speaker = { playing: string | null; loading: string | null; speak: (id: string, text: string) => void };

export function Welcome({ name, screenId, onSend, onFill }: {
    name: string; screenId: string; onSend: (text: string) => void; onFill: (text: string) => void;
}) {
    const cards = [
        { icon: Eye, title: "Explain this page", body: "What it's for, what to do here", run: () => onSend("What can I do on this page?") },
        { icon: WandSparkles, title: "Make a change", body: "Colours, knowledge, voice. Undo anytime", run: () => onFill("Change ") },
        { icon: Sparkles, title: "Build an assistant", body: "From your website, step by step", run: () => onSend("Create a new assistant from my website.") },
        { icon: PlugZap, title: "Connect a channel", body: "WhatsApp, a phone number, Cal.com", run: () => onSend("How do I connect my WhatsApp number?") },
    ];
    return (
        <div className="pt-3">
            <div className="flex flex-col items-center text-center">
                <img src="/agent/nimmi.svg" alt="" className="h-14 w-14 rounded-full border border-line shadow-sm" />
                <p className="mt-3 text-[15px] font-semibold">{name ? `Hi ${name}, I'm Nimmi` : "Hi, I'm Nimmi"}</p>
                <p className="mt-1 max-w-[19rem] text-[12.5px] leading-relaxed text-stone-600">
                    Your dashboard assistant. I look things up, make changes you can undo, and build assistants for you. Type, or tap the mic and talk.
                </p>
            </div>
            <div className="mt-5 grid grid-cols-2 gap-2">
                {cards.map((c) => (
                    <button key={c.title} type="button" onClick={c.run}
                            className="group rounded-lg border border-line bg-white px-3 py-2.5 text-left hover:border-plum/40 hover:bg-plum-tint/40 transition-colors">
                        <c.icon size={15} className="text-plum" aria-hidden />
                        <span className="mt-1.5 block text-[12.5px] font-medium text-ink">{c.title}</span>
                        <span className="block text-[11.5px] leading-snug text-stone-500">{c.body}</span>
                    </button>
                ))}
            </div>
            <p className="mt-5 mb-1.5 text-[11px] font-medium uppercase tracking-wide text-stone-400">For this page</p>
            <div className="flex flex-col items-start gap-1.5">
                {suggestionsFor(screenId).map((s) => (
                    <button key={s} type="button" onClick={() => onSend(s)}
                            className="text-left text-[12.5px] px-3 py-1.5 rounded-full border border-line-strong bg-white hover:bg-stone-50">
                        {s}
                    </button>
                ))}
            </div>
        </div>
    );
}

/** One of the person's messages. */
export function UserMessage({ text }: { text: string }) {
    return (
        <div className="flex justify-end">
            <p className="max-w-[85%] rounded-2xl rounded-br-md bg-plum-tint px-3 py-2 whitespace-pre-wrap [overflow-wrap:anywhere]">{text}</p>
        </div>
    );
}

/** One of Nimmi's turns: her avatar, then what she did and said, then the answer's actions. */
export function NimmiTurn({ items, latest, speaker, working }: { items: Item[]; latest: boolean; speaker: Speaker; working: boolean }) {
    const answer = [...items].reverse().find((i) => i.type === "text" && i.text) as Extract<Item, { type: "text" }> | undefined;
    return (
        <div className="group flex gap-2.5">
            <img src="/agent/nimmi.svg" alt="" className="mt-0.5 h-6 w-6 shrink-0 rounded-full border border-line" />
            <div className="min-w-0 flex-1 space-y-2">
                <p className="text-[12px] font-semibold text-stone-700 leading-6">Nimmi</p>
                {items.map((item) => <Part key={item.id} item={item} />)}
                {answer && !(latest && working) && <Actions answer={answer} latest={latest} speaker={speaker} />}
            </div>
        </div>
    );
}

function Actions({ answer, latest, speaker }: { answer: Extract<Item, { type: "text" }>; latest: boolean; speaker: Speaker }) {
    const agent = useAgent()!;
    const [copied, setCopied] = useState(false);
    const copy = () => navigator.clipboard.writeText(answer.text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); });
    const reading = speaker.playing === answer.id;
    const button = "h-7 w-7 rounded-md flex items-center justify-center text-stone-400 hover:text-ink hover:bg-stone-100";
    return (
        <div className={cn("-ml-1 flex items-center gap-0.5 transition-opacity", latest ? "opacity-100" : "opacity-0 group-hover:opacity-100 focus-within:opacity-100")}>
            <button type="button" onClick={copy} aria-label="Copy the answer" title="Copy" className={button}>
                {copied ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
            </button>
            <button type="button" onClick={() => speaker.speak(answer.id, answer.text)} aria-label={reading ? "Stop reading" : "Read aloud"}
                    title={reading ? "Stop" : "Read aloud"} className={cn(button, reading && "text-plum")}>
                {speaker.loading === answer.id ? <Loader2 size={14} className="animate-spin" /> : reading ? <Square size={12} fill="currentColor" /> : <Volume2 size={14} />}
            </button>
            {answer.runId && (
                <>
                    <button type="button" onClick={() => agent.rate(answer.id, "up")} aria-label="Good answer" aria-pressed={answer.rated === "up"}
                            title="Good answer" className={cn(button, answer.rated === "up" && "text-emerald-600")}>
                        <ThumbsUp size={14} />
                    </button>
                    <button type="button" onClick={() => agent.rate(answer.id, "down")} aria-label="Bad answer" aria-pressed={answer.rated === "down"}
                            title="Bad answer" className={cn(button, answer.rated === "down" && "text-signal")}>
                        <ThumbsDown size={14} />
                    </button>
                </>
            )}
            {latest && !agent.running && (
                <button type="button" onClick={agent.retry} aria-label="Try again" title="Try again" className={button}>
                    <RotateCcw size={14} />
                </button>
            )}
            {answer.rated && <span className="ml-1 text-[11px] text-stone-400">Thanks for the feedback</span>}
        </div>
    );
}

function Part({ item }: { item: Item }) {
    const agent = useAgent()!;
    if (item.type === "step") {
        return (
            <p className="flex items-center gap-2 text-[12px] text-stone-500">
                {item.running ? <Loader2 size={13} className="animate-spin" aria-hidden />
                    : item.ok ? <Check size={13} className="text-emerald-600" aria-hidden />
                    : <CircleAlert size={13} className="text-amber-600" aria-hidden />}
                <span className={cn(item.undone && "line-through")}>{item.label}{!item.running && !item.ok ? " (didn't work)" : ""}</span>
                {item.undone && <span className="text-stone-400">Undone</span>}
                {item.undoable && !item.undone && (
                    <button type="button" onClick={() => agent.undo(item.actionId!)} disabled={item.busy}
                            className="ml-auto inline-flex items-center gap-1 text-[12px] font-medium text-plum hover:underline disabled:opacity-50">
                        <Undo2 size={12} aria-hidden /> Undo
                    </button>
                )}
            </p>
        );
    }
    if (item.type === "confirm") {
        const open = item.state === "proposed";
        const outcome: Record<string, string> = { done: "Done", cancelled: "Cancelled", expired: "Expired: ask again", failed: "Didn't work", confirming: "Working…" };
        return (
            <div className={cn("rounded-lg border px-3 py-2.5", open ? "border-plum/30 bg-plum-tint/60" : "border-line bg-stone-50")}>
                <p className="text-[13px] font-semibold">{item.title}</p>
                <p className="mt-0.5 text-[12.5px] text-stone-600">{item.summary}</p>
                {open ? (
                    <div className="mt-2.5 flex gap-2">
                        <button type="button" onClick={() => agent.decide(item.actionId, "confirm")} disabled={item.busy}
                                className="h-8 px-3 rounded-md bg-plum text-white text-[13px] font-medium hover:bg-plum-hover disabled:opacity-50">
                            {item.busy ? "Working…" : "Confirm"}
                        </button>
                        <button type="button" onClick={() => agent.decide(item.actionId, "cancel")} disabled={item.busy}
                                className="h-8 px-3 rounded-md border border-line-strong bg-white text-[13px] hover:bg-stone-50 disabled:opacity-50">
                            Cancel
                        </button>
                    </div>
                ) : (
                    <p className={cn("mt-1.5 text-[12px] font-medium", item.state === "done" ? "text-emerald-700" : item.state === "failed" ? "text-signal" : "text-stone-500")}>
                        {outcome[item.state] ?? item.state}{item.message && item.state === "failed" ? `: ${item.message}` : ""}
                    </p>
                )}
            </div>
        );
    }
    if (item.type === "card") return <AgentCard card={item.card} active={item.active} busy={item.busy} />;
    if (item.type === "note") return <p className="text-[12px] text-stone-500 italic">{item.text.replace(/^\(|\)$/g, "")}</p>;
    if (item.type === "error") {
        return <p role="alert" className="rounded-md border border-signal/20 bg-signal/5 px-3 py-2 text-[13px] text-signal">{item.text}</p>;
    }
    if (item.type === "text") return item.text ? <AgentText text={item.text} /> : null;
    return null;
}
