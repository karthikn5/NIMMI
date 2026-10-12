"use client";

import { useRef, useState } from "react";
import { Pause, Play, Plus, X } from "lucide-react";
import { Button, Input, PhraseInput, Segmented, Select, Switch, cn, useToast } from "@/components/ui";
import { apiUrl } from "@/lib/api";
import type { AmbienceKind, CollectField, FieldType, VoiceAgentConfig } from "@/lib/voice/types";

export const FIELD_TYPES: { value: FieldType; label: string }[] = [
    { value: "text", label: "Text" },
    { value: "number", label: "Number" },
    { value: "yes_no", label: "Yes / no" },
    { value: "choice", label: "One of a list" },
    { value: "date", label: "Date" },
    { value: "phone", label: "Phone number" },
    { value: "email", label: "Email" },
];

const SUGGESTIONS: CollectField[] = [
    { label: "Name", type: "text", description: "Full name", choices: [], required: true },
    { label: "Phone number", type: "phone", description: "Best number to reach them", choices: [], required: false },
    { label: "Email", type: "email", description: "", choices: [], required: false },
    { label: "Budget", type: "number", description: "In rupees", choices: [], required: false },
    { label: "Preferred date", type: "date", description: "When they'd like the appointment or visit", choices: [], required: false },
    { label: "Interested", type: "yes_no", description: "Whether they want to go ahead", choices: [], required: false },
];

/** The details the assistant should find out on each call; they become columns in Collected data. */
export function FieldsEditor({ value, onChange }: { value: CollectField[]; onChange: (v: CollectField[]) => void }) {
    const update = (i: number, patch: Partial<CollectField>) => onChange(value.map((f, j) => (j === i ? { ...f, ...patch } : f)));
    const used = new Set(value.map((f) => f.label.trim().toLowerCase()));
    const unusedSuggestions = SUGGESTIONS.filter((s) => !used.has(s.label.toLowerCase()));

    return (
        <div>
            {value.length > 0 && (
                <ul className="space-y-2 mb-3">
                    {value.map((f, i) => (
                        <li key={i} className="rounded-md border border-line p-3">
                            <div className="grid grid-cols-[minmax(0,1fr)_9.5rem_auto] gap-2 items-center">
                                <Input aria-label="Field name" placeholder="e.g. Budget" value={f.label} maxLength={40}
                                       onChange={(e) => update(i, { label: e.target.value })} />
                                <Select aria-label={`Type of ${f.label || "field"}`} value={f.type}
                                        onChange={(e) => update(i, { type: e.target.value as FieldType })}>
                                    {FIELD_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                                </Select>
                                <button type="button" onClick={() => onChange(value.filter((_, j) => j !== i))} aria-label={`Remove ${f.label || "field"}`}
                                        className="p-2 rounded text-stone-400 hover:text-signal hover:bg-red-50 focus-visible:outline-2 focus-visible:outline-plum">
                                    <X size={14} />
                                </button>
                            </div>
                            <Input aria-label="What it means" className="mt-2" placeholder="What it means, so the assistant asks clearly (optional)"
                                   value={f.description} maxLength={200} onChange={(e) => update(i, { description: e.target.value })} />
                            {f.type === "choice" && (
                                <div className="mt-2">
                                    <PhraseInput keepCase label={`Choices for ${f.label}`} value={f.choices}
                                                 onChange={(v) => update(i, { choices: v })} placeholder="Type a choice, press Enter" />
                                    {f.choices.length < 2 && <p className="text-xs text-stone-500 mt-1">Add at least two choices.</p>}
                                </div>
                            )}
                            <label className="flex items-center gap-2 mt-2.5 text-[13px] text-stone-600">
                                <Switch checked={f.required} onChange={(v) => update(i, { required: v })} label={`${f.label || "Field"} is required`} />
                                Must ask before ending the call
                            </label>
                        </li>
                    ))}
                </ul>
            )}
            <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" onClick={() => onChange([...value, { label: "", type: "text", description: "", choices: [], required: false }])}>
                    <Plus size={13} /> Add field
                </Button>
                {unusedSuggestions.slice(0, 4).map((s) => (
                    <button key={s.label} type="button" onClick={() => onChange([...value, s])}
                            className="h-7 px-2.5 rounded-full border border-dashed border-line-strong text-xs text-stone-600 hover:border-plum hover:text-plum focus-visible:outline-2 focus-visible:outline-plum">
                        + {s.label}
                    </button>
                ))}
            </div>
        </div>
    );
}

export function PronunciationEditor({ value, onChange }: {
    value: VoiceAgentConfig["pronunciations"]; onChange: (v: VoiceAgentConfig["pronunciations"]) => void;
}) {
    const update = (i: number, key: "word" | "say", text: string) => onChange(value.map((p, j) => (j === i ? { ...p, [key]: text } : p)));
    return (
        <div>
            {value.length > 0 && (
                <ul className="space-y-2 mb-3">
                    {value.map((p, i) => (
                        <li key={i} className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto] gap-2 items-center">
                            <Input aria-label="Written as" placeholder="Written as, e.g. Nimmi" value={p.word} maxLength={40} onChange={(e) => update(i, "word", e.target.value)} />
                            <span className="text-xs text-stone-400" aria-hidden>say</span>
                            <Input aria-label="Said as" placeholder="Said as, e.g. Nim-mee" value={p.say} maxLength={80} onChange={(e) => update(i, "say", e.target.value)} />
                            <button type="button" onClick={() => onChange(value.filter((_, j) => j !== i))} aria-label={`Remove ${p.word || "rule"}`}
                                    className="p-2 rounded text-stone-400 hover:text-signal hover:bg-red-50 focus-visible:outline-2 focus-visible:outline-plum">
                                <X size={14} />
                            </button>
                        </li>
                    ))}
                </ul>
            )}
            <Button size="sm" onClick={() => onChange([...value, { word: "", say: "" }])}><Plus size={13} /> Add word</Button>
        </div>
    );
}

const AMBIENCE: { value: AmbienceKind; label: string }[] = [
    { value: "none", label: "None (Crystal Clean)" },
    { value: "subtle_room", label: "Subtle Room Tone (Calm & Natural)" },
    { value: "quiet_office", label: "Quiet Office (Professional)" },
    { value: "call_center", label: "Call Center (Gentle Murmur)" },
    { value: "executive_suite", label: "Executive Suite (Muffled Soft)" },
    { value: "comfort_noise", label: "Telecom Comfort Noise (Warm Line)" },
    { value: "cafe", label: "Café (Soft Background)" },
];

export function AmbiencePicker({ kind, volume, onKind, onVolume }: {
    kind: AmbienceKind; volume: VoiceAgentConfig["ambience_volume"];
    onKind: (k: AmbienceKind) => void; onVolume: (v: VoiceAgentConfig["ambience_volume"]) => void;
}) {
    const toast = useToast();
    const audio = useRef<HTMLAudioElement | null>(null);
    const [playing, setPlaying] = useState(false);

    const toggle = () => {
        if (playing) {
            audio.current?.pause();
            setPlaying(false);
            return;
        }
        const a = new Audio(apiUrl(`/api/voice/ambience/${kind}/sample?volume=${volume}`));
        audio.current?.pause();
        audio.current = a;
        a.onended = () => setPlaying(false);
        a.play().then(() => setPlaying(true)).catch(() => toast("Couldn't play the sample."));
    };

    return (
        <div className="space-y-3">
            <div className="flex items-center gap-2">
                <Select aria-label="Background sound" className="max-w-72" value={kind}
                        onChange={(e) => { audio.current?.pause(); setPlaying(false); onKind(e.target.value as AmbienceKind); }}>
                    {AMBIENCE.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
                </Select>
                {kind !== "none" && (
                    <Button size="sm" variant="ghost" onClick={toggle} aria-label={playing ? "Stop sample" : "Play sample"}>
                        {playing ? <Pause size={13} /> : <Play size={13} />} {playing ? "Stop" : "Listen"}
                    </Button>
                )}
            </div>
            <div className={cn(kind === "none" && "opacity-50 pointer-events-none")}>
                <Segmented label="Background volume" value={volume} onChange={(v) => { audio.current?.pause(); setPlaying(false); onVolume(v); }}
                           options={[
                               { value: "subtle", label: "Subtle (Calm)" },
                               { value: "low", label: "Low" },
                               { value: "medium", label: "Medium" },
                               { value: "high", label: "High" },
                           ]} />
            </div>
            <p className="text-xs text-stone-500">
                Acoustically softened and automatically ducked during assistant speech so callers are never disturbed.
            </p>
        </div>
    );
}
