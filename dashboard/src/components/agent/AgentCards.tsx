"use client";

import { useState } from "react";
import Link from "next/link";
import { Check, ExternalLink, Globe, Phone, Sparkles } from "lucide-react";
import { cn } from "@/components/ui";
import { useAgent } from "./AgentProvider";

/**
 * The cards of "create an agent for me" (backend/agent/builder.py): the website (or a description), the name and
 * look, phone calls or not, and the finished assistant. A card can be used while its step waits for the person; once
 * done it stays in the chat as a short record.
 */
export type Card = {
    kind: "source" | "look" | "voice" | "result" | "guide";
    jobId: string;
    botId?: string;
    name?: string;
    names?: string[];
    colours?: string[];
    logo?: string | null;
    font?: string | null;
    voice?: boolean;
    tryUrl?: string;
    builderUrl?: string;
    numbersUrl?: string | null;
    questions?: string[];
    // A guide (connecting Twilio, Exotel, WhatsApp or Cal.com): the steps end at Nimmi's own form.
    title?: string;
    why?: string;
    link?: string;
    link_label?: string;
    form?: string | null;
    form_label?: string;
    steps?: string[];
    note?: string;
};

const box = "rounded-lg border px-3 py-3 text-[13px]";
const primary = "h-8 px-3 rounded-md bg-plum text-white text-[13px] font-medium hover:bg-plum-hover disabled:opacity-50";
const secondary = "h-8 px-3 rounded-md border border-line-strong bg-white text-[13px] hover:bg-stone-50 disabled:opacity-50";
const field = "w-full h-9 rounded-md border border-line-strong bg-white px-2.5 text-[13px] outline-none focus:border-plum";

export default function AgentCard({ card, active, busy }: { card: Card; active: boolean; busy?: boolean }) {
    if (card.kind === "result") return <Result card={card} />;
    if (card.kind === "guide") return <Guide card={card} />;
    if (!active) return <Done card={card} busy={busy} />;
    if (card.kind === "source") return <Source card={card} busy={busy} />;
    if (card.kind === "look") return <Look card={card} busy={busy} />;
    return <Voice card={card} busy={busy} />;
}

function Done({ card, busy }: { card: Card; busy?: boolean }) {
    const words = { source: "Website", look: "Name and look", voice: "Phone calls", result: "", guide: "Steps" }[card.kind];
    return (
        <p className="flex items-center gap-2 text-[12px] text-stone-500">
            <Check size={13} className={busy ? "text-stone-400" : "text-emerald-600"} aria-hidden />
            {words}{busy ? ": working on it…" : ": done"}
        </p>
    );
}

function Source({ card, busy }: { card: Card; busy?: boolean }) {
    const agent = useAgent()!;
    const [url, setUrl] = useState("");
    const [describe, setDescribe] = useState(false);
    const [text, setText] = useState("");
    const go = () => agent.jobStep(card.jobId, "source", describe ? { description: text } : { url });
    return (
        <div className={cn(box, "border-plum/30 bg-plum-tint/60")}>
            <p className="font-semibold flex items-center gap-1.5"><Sparkles size={14} aria-hidden /> Build an assistant</p>
            {describe ? (
                <>
                    <p className="mt-1 text-stone-600">Describe your business: what you offer, prices, timings, where you are, how to book.</p>
                    <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} maxLength={6000} aria-label="Describe your business"
                              className={cn(field, "h-auto py-2 mt-2 resize-y")} />
                    <div className="mt-2 flex items-center gap-2">
                        <button type="button" className={primary} disabled={busy || text.trim().length < 40} onClick={go}>Continue</button>
                        <button type="button" className="text-[12px] text-plum hover:underline" onClick={() => setDescribe(false)}>I have a website</button>
                    </div>
                </>
            ) : (
                <>
                    <p className="mt-1 text-stone-600">I&apos;ll read your website, then set up the knowledge, instructions, welcome flow and lead capture. It takes a minute or two.</p>
                    <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (url.trim()) go(); }}>
                        <div className="relative flex-1">
                            <Globe size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-stone-400" aria-hidden />
                            <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="yourbusiness.com" aria-label="Your website"
                                   inputMode="url" className={cn(field, "pl-8")} />
                        </div>
                        <button type="submit" className={primary} disabled={busy || !url.trim()}>Read it</button>
                    </form>
                    <button type="button" className="mt-2 text-[12px] text-plum hover:underline" onClick={() => setDescribe(true)}>
                        No website? Describe your business
                    </button>
                </>
            )}
        </div>
    );
}

function Look({ card, busy }: { card: Card; busy?: boolean }) {
    const agent = useAgent()!;
    const names = card.names?.length ? card.names : ["Assistant"];
    const colours = card.colours?.length ? card.colours : ["#550a64"];
    const [name, setName] = useState(names[0]);
    const [colour, setColour] = useState(colours[0]);
    const [useLogo, setUseLogo] = useState(!!card.logo);
    return (
        <div className={cn(box, "border-plum/30 bg-plum-tint/60 space-y-3")}>
            <p className="font-semibold">Its name and look</p>
            <div>
                <p className="text-[12px] text-stone-600 mb-1.5">Name</p>
                <div className="flex flex-wrap gap-1.5">
                    {names.map((n) => (
                        <button key={n} type="button" onClick={() => setName(n)} aria-pressed={name === n}
                                className={cn("h-7 px-2.5 rounded-full border text-[12.5px]", name === n ? "border-plum bg-white text-plum font-medium" : "border-line-strong bg-white")}>
                            {n}
                        </button>
                    ))}
                </div>
                <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} aria-label="Assistant name" className={cn(field, "mt-2")} />
            </div>
            <div>
                <p className="text-[12px] text-stone-600 mb-1.5">Colour{colours.length > 1 ? ", from your website" : ""}</p>
                <div className="flex gap-2">
                    {colours.map((c) => (
                        <button key={c} type="button" onClick={() => setColour(c)} aria-label={`Colour ${c}`} aria-pressed={colour === c}
                                className={cn("h-8 w-8 rounded-full border-2", colour === c ? "border-ink" : "border-white shadow-[0_0_0_1px_#d6d1ca]")}
                                style={{ background: c }} />
                    ))}
                </div>
            </div>
            {card.logo && (
                <label className="flex items-center gap-2.5">
                    <input type="checkbox" checked={useLogo} onChange={(e) => setUseLogo(e.target.checked)} className="accent-plum" />
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={card.logo} alt="" referrerPolicy="no-referrer" style={{ background: colour }}
                         className="h-9 w-9 rounded-full border border-line object-contain p-1" />
                    <span>Use your logo as its picture</span>
                </label>
            )}
            {card.font && <p className="text-[12px] text-stone-500">Font from your website: {card.font}</p>}
            <button type="button" className={primary} disabled={busy || !name.trim()}
                    onClick={() => agent.jobStep(card.jobId, "look", { name: name.trim(), colour, use_logo: useLogo })}>
                Looks good
            </button>
        </div>
    );
}

function Voice({ card, busy }: { card: Card; busy?: boolean }) {
    const agent = useAgent()!;
    return (
        <div className={cn(box, "border-plum/30 bg-plum-tint/60")}>
            <p className="font-semibold flex items-center gap-1.5"><Phone size={14} aria-hidden /> Phone calls too?</p>
            <p className="mt-1 text-stone-600">
                {card.name ?? "It"} can also answer phone calls in a natural Indian voice, in the caller&apos;s language. I&apos;ll set it up now;
                it starts answering once you connect a number.
            </p>
            <div className="mt-2.5 flex gap-2">
                <button type="button" className={primary} disabled={busy} onClick={() => agent.jobStep(card.jobId, "voice", { on: true })}>Yes, set it up</button>
                <button type="button" className={secondary} disabled={busy} onClick={() => agent.jobStep(card.jobId, "voice", { on: false })}>Not now</button>
            </div>
        </div>
    );
}

function Result({ card }: { card: Card }) {
    return (
        <div className={cn(box, "border-emerald-600/25 bg-emerald-50/60")}>
            <p className="font-semibold flex items-center gap-1.5"><Check size={14} className="text-emerald-700" aria-hidden /> {card.name} is ready</p>
            <div className="mt-2 flex flex-wrap gap-2">
                {card.tryUrl && (
                    <a href={card.tryUrl} target="_blank" rel="noopener noreferrer" className={cn(primary, "inline-flex items-center gap-1.5")}>
                        Try it <ExternalLink size={12} aria-hidden />
                    </a>
                )}
                {card.builderUrl && <Link href={card.builderUrl} className={cn(secondary, "inline-flex items-center")}>Open in the builder</Link>}
                {card.numbersUrl && <Link href={card.numbersUrl} className={cn(secondary, "inline-flex items-center")}>Connect a number</Link>}
            </div>
            {!!card.questions?.length && (
                <div className="mt-2.5">
                    <p className="text-[12px] text-stone-600">Try asking it:</p>
                    <ul className="mt-1 list-disc pl-5 text-[12.5px] text-stone-700">
                        {card.questions.map((q) => <li key={q}>{q}</li>)}
                    </ul>
                </div>
            )}
            <p className="mt-2 text-[12px] text-stone-500">To put it on your website: open it in the builder, then &ldquo;Add to website&rdquo;.</p>
        </div>
    );
}

function Guide({ card }: { card: Card }) {
    return (
        <div className={cn(box, "border-line bg-white")}>
            <p className="font-semibold">{card.title}</p>
            {card.why && <p className="mt-0.5 text-stone-600">{card.why}</p>}
            <ol className="mt-2 list-decimal pl-5 space-y-1.5 text-[12.5px] text-stone-700">
                {(card.steps ?? []).map((step, i) => <li key={i}>{step}</li>)}
            </ol>
            <div className="mt-3 flex flex-wrap gap-2">
                {card.link && (
                    <a href={card.link} target="_blank" rel="noopener noreferrer" className={cn(secondary, "inline-flex items-center gap-1.5")}>
                        {card.link_label ?? "Open"} <ExternalLink size={12} aria-hidden />
                    </a>
                )}
                {card.form && <Link href={card.form} className={cn(primary, "inline-flex items-center")}>Open the form in Nimmi</Link>}
            </div>
            {card.form_label && !card.form && <p className="mt-2 text-[12px] text-stone-500">In Nimmi: {card.form_label}.</p>}
            {card.note && <p className="mt-2 text-[12px] text-stone-500">{card.note}</p>}
            <p className="mt-2 text-[12px] text-stone-500">Paste keys only into Nimmi&apos;s form, never into this chat.</p>
        </div>
    );
}
