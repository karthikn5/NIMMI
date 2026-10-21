"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Check, X } from "lucide-react";
import { Button, Dialog, Input, Segmented, Select, Textarea, cn } from "@/components/ui";
import { Field, Section, ToggleRow } from "./controls";
import { LANGUAGES, MAX_CUSTOM_FIELDS, STANDARD_FIELDS, type Behaviour, type Collect } from "./design";

const TIMING_HINT: Record<Collect["timing"], string> = {
    early: "Asks for the first detail right after its first answer. Best when every chat should become a lead.",
    after_answer: "Answers the question first, then asks for one detail when it fits. Works for most businesses.",
    interest: "Asks only once the visitor shows real interest: prices, booking, a visit, a quote or a callback.",
};

/** Starting points for the instructions; each is a complete, editable brief. */
const TEMPLATES = [
    { name: "Front desk", text: "You are the friendly front desk for our business. Greet visitors, answer questions about our timings, location, services and prices, and point them to the right next step. Use simple, polite language." },
    { name: "Sales", text: "You help visitors find the right product or service. Ask one question at a time to understand what they need, recommend the best fit, and mention prices when you know them. When they're interested, invite them to share their name and phone number so our team can follow up." },
    { name: "Appointments", text: "You help visitors book appointments, site visits or consultations. Find out what they need and when they're free, suggest a suitable time, and repeat the details back to them. Never promise a slot; say our team will confirm it." },
    { name: "Support", text: "You help customers with questions and problems about our products and services. Be patient and give clear, step-by-step help. If someone is unhappy, apologise once, acknowledge the problem and offer to connect them with our team." },
];

type Props = {
    instructions: string;
    setInstructions: (v: string) => void;
    behaviour: Behaviour;
    setBehaviour: (patch: Partial<Behaviour>) => void;
    /** Thumbs up/down under answers in the widget (a widget setting, saved with the design). */
    rateAnswers: boolean;
    setRateAnswers: (v: boolean) => void;
};

export default function BehaviourPanel({ instructions, setInstructions, behaviour: b, setBehaviour, rateAnswers, setRateAnswers }: Props) {
    const [pending, setPending] = useState<(typeof TEMPLATES)[number] | null>(null);
    const applyTemplate = (t: (typeof TEMPLATES)[number]) => (instructions.trim() ? setPending(t) : setInstructions(t.text));

    return (
        <div>
            <Section title="Instructions" description="Tell the assistant who it works for, what it should do and anything it must never say. Write it as you would brief a new employee.">
                <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-[12px] text-stone-500 mr-1">Start from</span>
                    {TEMPLATES.map((t) => (
                        <button key={t.name} type="button" onClick={() => applyTemplate(t)}
                                className="h-7 px-2.5 rounded-md border border-line-strong bg-white text-[12px] text-stone-700 hover:border-stone-400 hover:text-ink transition-colors">
                            {t.name}
                        </button>
                    ))}
                </div>
                <Textarea rows={9} value={instructions} onChange={(e) => setInstructions(e.target.value)} aria-label="Instructions"
                          placeholder="e.g. You work for Green Park Homes, a builder in Chennai. Help visitors choose a home, share prices from the information you have, and book site visits. Never discuss other builders."
                          className="text-[13px]" />
                <p className="text-[12px] text-stone-500 tabular-nums">{instructions.length.toLocaleString("en-IN")} characters</p>
            </Section>

            <Section title="How it replies">
                <Field label="Reply length">
                    <Segmented label="Reply length" value={b.reply_length} onChange={(v) => setBehaviour({ reply_length: v })}
                               options={[{ value: "short", label: "Short" }, { value: "balanced", label: "Balanced" }, { value: "detailed", label: "Detailed" }]} />
                </Field>
                <Field label="Language" htmlFor="reply-language" hint="“Same as the visitor” also follows mixes like Tanglish and Hinglish.">
                    <Select id="reply-language" value={b.language} onChange={(e) => setBehaviour({ language: e.target.value })}>
                        {LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
                    </Select>
                </Field>
                <ToggleRow label="Offer a person when it can't help" hint="Tells visitors they can ask for someone from your team, who replies from Live chat."
                           checked={b.offer_human} onChange={(v) => setBehaviour({ offer_human: v })} />
            </Section>

            <CollectSettings collect={b.collect} onChange={(patch) => setBehaviour({ collect: { ...b.collect, ...patch } })} />

            <Section title="When it doesn't know" description="It never makes things up. It says it doesn't have that information, then adds your next step.">
                <Field label="Then say" htmlFor="fallback">
                    <Input id="fallback" value={b.fallback_followup} maxLength={300} onChange={(e) => setBehaviour({ fallback_followup: e.target.value })}
                           placeholder="e.g. You can call us on 044 4567 8900, 9 AM to 7 PM." />
                </Field>
                <div className="rounded-md bg-stone-50 border border-line px-3 py-2.5 text-[13px] text-stone-700">
                    <span className="text-stone-500">Visitors will see: </span>
                    “I&apos;m sorry, I don&apos;t have that information.{b.fallback_followup.trim() ? ` ${b.fallback_followup.trim()}` : ""}”
                </div>
                <p className="text-[12px] text-stone-500">These questions are collected in Questions, so you can answer them once.</p>
            </Section>

            <Section title="Learn from visitors">
                <ToggleRow label="Let visitors rate answers" hint="Adds “Helpful?” with thumbs up and down under each answer. Answers marked unhelpful go to Questions, so you can fix them."
                           checked={rateAnswers} onChange={setRateAnswers} />
            </Section>

            <Section title="Business hours and escalation">
                <Link href="/dashboard/live-chat" className="flex items-center justify-between gap-3 rounded-md border border-line px-4 py-3 hover:bg-stone-50 transition-colors">
                    <span className="text-[13px] text-stone-600">Opening hours, the away message and bringing in your team for upset customers are set in Live chat.</span>
                    <ArrowRight size={16} className="text-stone-400 shrink-0" />
                </Link>
            </Section>

            <Dialog open={!!pending} onClose={() => setPending(null)} title="Replace your instructions?"
                    description={`This replaces what you've written with the ${pending?.name ?? ""} template. You can edit it afterwards.`}
                    footer={<>
                        <Button variant="ghost" onClick={() => setPending(null)}>Cancel</Button>
                        <Button variant="primary" onClick={() => { if (pending) setInstructions(pending.text); setPending(null); }}>Replace</Button>
                    </>}>
                <p className="text-[13px] text-stone-600 leading-relaxed">{pending?.text}</p>
            </Dialog>
        </div>
    );
}

/** Which details the assistant finds out during the chat (see backend/brain.py). */
function CollectSettings({ collect: c, onChange }: { collect: Collect; onChange: (patch: Partial<Collect>) => void }) {
    const [draft, setDraft] = useState("");
    const taken = (label: string) => [...STANDARD_FIELDS.map((f) => f.label), ...c.custom].some((l) => l.toLowerCase() === label.toLowerCase());
    const label = draft.replace(/\s+/g, " ").trim().slice(0, 40);
    const canAdd = !!label && !taken(label) && c.custom.length < MAX_CUSTOM_FIELDS;
    const add = () => {
        if (!canAdd) return;
        onChange({ custom: [...c.custom, label] });
        setDraft("");
    };
    const toggle = (field: Collect["fields"][number]) =>
        onChange({ fields: c.fields.includes(field) ? c.fields.filter((f) => f !== field) : STANDARD_FIELDS.map((f) => f.value).filter((f) => f === field || c.fields.includes(f)) });
    const nothing = !c.fields.length && !c.custom.length;

    return (
        <Section title="Details to collect" description="The assistant asks for these during the chat, one at a time and never twice. Details a visitor mentions on their own are saved too. You'll find them in Leads.">
            <ToggleRow label="Collect visitor details" hint="Turn off if the assistant should only answer questions."
                       checked={c.enabled} onChange={(v) => onChange({ enabled: v })} />
            {c.enabled && (
                <>
                    <Field label="Ask for">
                        <div className="flex flex-wrap gap-1.5">
                            {STANDARD_FIELDS.map((f) => {
                                const on = c.fields.includes(f.value);
                                return (
                                    <button key={f.value} type="button" role="checkbox" aria-checked={on} onClick={() => toggle(f.value)}
                                            className={cn("inline-flex items-center gap-1.5 h-8 px-3 rounded-md border text-[13px] transition-colors",
                                                          on ? "border-plum bg-plum/5 text-ink" : "border-line-strong bg-white text-stone-500 hover:text-ink")}>
                                        {on && <Check size={13} className="text-plum" aria-hidden />} {f.label}
                                    </button>
                                );
                            })}
                            {c.custom.map((l) => (
                                <span key={l} className="inline-flex items-center gap-1 h-8 pl-3 pr-1 rounded-md border border-plum bg-plum/5 text-[13px] text-ink">
                                    {l}
                                    <button type="button" onClick={() => onChange({ custom: c.custom.filter((x) => x !== l) })} aria-label={`Stop asking for ${l}`}
                                            className="p-1 rounded text-stone-400 hover:text-signal hover:bg-red-50">
                                        <X size={13} />
                                    </button>
                                </span>
                            ))}
                        </div>
                    </Field>
                    {c.custom.length < MAX_CUSTOM_FIELDS && (
                        <Field label="Your own details" htmlFor="custom-detail" hint="For example Budget, City, Preferred date or Number of guests.">
                            <div className="flex gap-2">
                                <Input id="custom-detail" value={draft} maxLength={40} onChange={(e) => setDraft(e.target.value)}
                                       onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} placeholder="e.g. Budget" />
                                <Button onClick={add} disabled={!canAdd}>Add</Button>
                            </div>
                            {!!label && taken(label) && <p className="mt-1.5 text-[12px] text-stone-500">{label} is already on the list.</p>}
                        </Field>
                    )}
                    {nothing ? (
                        <p className="text-[13px] text-amber-700">Choose at least one detail, or turn collecting off.</p>
                    ) : (
                        <Field label="When to ask" hint={TIMING_HINT[c.timing]}>
                            <Segmented label="When to ask" value={c.timing} onChange={(v) => onChange({ timing: v })}
                                       options={[{ value: "early", label: "Early" }, { value: "after_answer", label: "After answering" }, { value: "interest", label: "When interested" }]} />
                        </Field>
                    )}
                </>
            )}
        </Section>
    );
}
