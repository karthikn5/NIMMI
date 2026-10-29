"use client";

import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import Link from "next/link";
import { Check, ChevronDown, Play, Search } from "lucide-react";
import { Skeleton, cn } from "@/components/ui";
import { LANGUAGES, formatNumber, formatRate } from "@/lib/voice/api";
import type { AgentDetails, LanguageCode, Voice, VoiceModel, VoiceModels } from "@/lib/voice/types";

// From the caller stopping to the agent's first sound, apart from the model (backend REPLY_OVERHEAD_SEC).
const REPLY_OVERHEAD_SEC = 0.35;
const MAKER_DOT: Record<string, string> = {
    OpenAI: "bg-emerald-600", Anthropic: "bg-orange-600", Google: "bg-sky-600", "Sarvam AI": "bg-amber-500", Alibaba: "bg-violet-600",
};

const perMinute = (n: number) => `${formatRate(n)}/min`;
const seconds = (n: number) => `${new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 }).format(n)} s`;

type Option = { id: string; disabled?: boolean; heading?: string };

/** A button that opens a list to pick from. Arrow keys move, Enter picks, Escape or a click outside closes it. */
function Dropdown<T extends Option>({ label, button, options, value, onPick, renderOption, header, footer, width = "w-80" }: {
    label: string; button: ReactNode; options: T[]; value: string; onPick: (id: string) => void;
    renderOption: (o: T, active: boolean) => ReactNode; header?: ReactNode; footer?: ReactNode; width?: string;
}) {
    const [open, setOpen] = useState(false);
    const [active, setActive] = useState(-1);
    const box = useRef<HTMLDivElement>(null);
    const list = useRef<HTMLUListElement>(null);
    const id = useId();

    useEffect(() => {
        if (!open) return;
        const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
        document.addEventListener("mousedown", away);
        return () => document.removeEventListener("mousedown", away);
    }, [open]);
    useEffect(() => {
        if (open && active >= 0) list.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
    }, [open, active]);

    const show = () => { setOpen(true); setActive(Math.max(0, options.findIndex((o) => o.id === value))); };
    const step = (from: number, by: number) => {
        for (let i = 1; i <= options.length; i++) {
            const next = (from + by * i + options.length) % options.length;
            if (!options[next].disabled) return next;
        }
        return from;
    };
    const onKey = (e: KeyboardEvent) => {
        if (e.key === "Escape") { setOpen(false); return; }
        if (!open && (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ")) { e.preventDefault(); show(); return; }
        if (!open) return;
        if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); setActive((a) => step(a, e.key === "ArrowDown" ? 1 : -1)); }
        if (e.key === "Enter" && options[active] && !options[active].disabled) { e.preventDefault(); onPick(options[active].id); setOpen(false); }
    };

    return (
        <div ref={box} className="relative" onKeyDown={onKey}>
            <button type="button" aria-haspopup="listbox" aria-expanded={open} aria-controls={id} aria-label={label}
                    onClick={() => (open ? setOpen(false) : show())}
                    className={cn("h-9 pl-3 pr-2 inline-flex items-center gap-2 rounded-md border bg-white text-sm transition-colors",
                                  "focus-visible:outline-2 focus-visible:outline-plum max-w-full",
                                  open ? "border-plum" : "border-line-strong hover:border-stone-400")}>
                {button}
                <ChevronDown size={14} className={cn("shrink-0 text-stone-500 transition-transform", open && "rotate-180")} aria-hidden />
            </button>
            {open && (
                <div className={cn("absolute left-0 top-full mt-1.5 z-30 max-w-[calc(100vw-2rem)] rounded-lg border border-line bg-white",
                                   "shadow-[0_12px_32px_rgba(28,23,25,0.14)] overflow-hidden", width)}>
                    {header}
                    <ul ref={list} id={id} role="listbox" aria-label={label} className="max-h-[22rem] overflow-y-auto py-1">
                        {options.map((o, i) => (
                            <li key={o.id} role={o.heading ? "presentation" : "option"} data-index={i}
                                aria-selected={o.heading ? undefined : o.id === value} aria-disabled={(!o.heading && o.disabled) || undefined}
                                onMouseEnter={() => !o.disabled && setActive(i)}
                                onClick={() => { if (!o.disabled) { onPick(o.id); setOpen(false); } }}
                                className={cn(o.disabled ? "cursor-not-allowed" : "cursor-pointer")}>
                                {renderOption(o, i === active)}
                            </li>
                        ))}
                    </ul>
                    {footer}
                </div>
            )}
        </div>
    );
}

type ModelRow = Option & { model?: VoiceModel; heading?: string };

/** The AI model the agent answers with, grouped like other voice platforms, each with what a call minute costs. */
export function ModelMenu({ value, onChange, models }: { value: string; onChange: (id: string) => void; models?: VoiceModels | null }) {
    const [query, setQuery] = useState("");
    const rows = useMemo<ModelRow[]>(() => {
        if (!models) return [];
        const q = query.trim().toLowerCase();
        const shown = models.models.filter((m) => !q || `${m.name} ${m.maker}`.toLowerCase().includes(q));
        return (Object.keys(models.groups) as VoiceModel["group"][]).flatMap((g) => {
            const inGroup = shown.filter((m) => m.group === g);
            return inGroup.length ? [{ id: `group-${g}`, heading: models.groups[g], disabled: true }, ...inGroup.map((m) => ({ id: m.id, model: m, disabled: !m.available }))] : [];
        });
    }, [models, query]);
    if (!models) return <Skeleton className="h-9 w-56" />;
    const selected = models.models.find((m) => m.id === value) ?? models.models.find((m) => m.id === models.default);

    return (
        <Dropdown<ModelRow>
            label="AI model"
            width="w-[26rem]"
            value={value}
            options={rows}
            onPick={(id) => { onChange(id); setQuery(""); }}
            button={selected ? (
                <>
                    <span className={cn("h-2 w-2 rounded-full shrink-0", MAKER_DOT[selected.maker] ?? "bg-stone-400")} aria-hidden />
                    <span className="font-medium truncate">{selected.name}</span>
                </>
            ) : "Choose a model"}
            header={(
                <div className="p-2 border-b border-line">
                    <label className="flex items-center gap-2 h-8 px-2.5 rounded-md bg-stone-50 border border-line focus-within:border-plum">
                        <Search size={13} className="text-stone-400" aria-hidden />
                        <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search models" aria-label="Search models"
                               className="flex-1 bg-transparent text-[13px] outline-none placeholder:text-stone-400" />
                    </label>
                </div>
            )}
            footer={(
                <p className="px-3 py-2 border-t border-line text-[12px] leading-snug text-stone-500">
                    Prices include the voice and phone line ({formatNumber(models.base_credits)} credit a minute). Calls are counted in half-minutes.{" "}
                    <Link href="/dashboard/billing#rates" className="text-plum hover:underline">All rates</Link>
                </p>
            )}
            renderOption={(row, active) => row.heading ? (
                <p className="px-3 pt-2.5 pb-1 text-[11px] font-medium uppercase tracking-[0.06em] text-stone-500">{row.heading}</p>
            ) : (
                <div title={row.model!.about} className={cn("mx-1 px-2.5 py-2 rounded-md flex items-center gap-2.5",
                                                            active && "bg-stone-100", row.disabled && "opacity-50")}>
                    <span className={cn("h-2 w-2 rounded-full shrink-0", MAKER_DOT[row.model!.maker] ?? "bg-stone-400")} aria-hidden />
                    <span className="flex-1 min-w-0 flex items-center gap-1.5">
                        <span className="text-[13px] font-medium truncate">{row.model!.name}</span>
                        {row.model!.suggested && <span className="shrink-0 text-[11px] px-1.5 rounded bg-plum-tint text-plum">Suggested</span>}
                        {row.model!.preview && <span className="shrink-0 text-[11px] px-1.5 rounded bg-stone-100 text-stone-600">Preview</span>}
                    </span>
                    <span className="shrink-0 text-right text-[12px] tabular-nums text-stone-500 leading-tight">
                        {row.disabled ? "Coming soon" : (
                            <>
                                <span className="text-ink">{perMinute(row.model!.credits_per_minute)}</span>
                                {row.model!.first_words_sec !== null && <span className="block">{seconds(row.model!.first_words_sec)}</span>}
                            </>
                        )}
                    </span>
                    {row.id === value ? <Check size={14} className="text-plum shrink-0" aria-hidden /> : <span className="w-3.5 shrink-0" />}
                </div>
            )}
        />
    );
}

/** The voice callers hear, with a sample of each. */
export function VoiceMenu({ value, onChange, voices, onPlay }: {
    value: string | null; onChange: (id: string) => void; voices?: Voice[] | null; onPlay: (v: Voice) => void;
}) {
    if (!voices) return <Skeleton className="h-9 w-36" />;
    const selected = voices.find((v) => v.id === value);
    return (
        <Dropdown<Voice>
            label="Voice"
            width="w-72"
            value={value ?? ""}
            options={voices}
            onPick={onChange}
            button={selected ? (
                <>
                    <span className="h-5 w-5 rounded-full bg-plum-tint text-plum text-[11px] font-semibold flex items-center justify-center shrink-0" aria-hidden>
                        {selected.name[0]}
                    </span>
                    <span className="font-medium">{selected.name}</span>
                </>
            ) : <span className="text-stone-500">Choose a voice</span>}
            renderOption={(v, active) => (
                <div className={cn("mx-1 pl-2.5 pr-1.5 py-1.5 rounded-md flex items-center gap-2.5", active && "bg-stone-100")}>
                    <span className="h-6 w-6 rounded-full bg-plum-tint text-plum text-[11px] font-semibold flex items-center justify-center shrink-0" aria-hidden>
                        {v.name[0]}
                    </span>
                    <span className="flex-1 min-w-0">
                        <span className="block text-[13px] font-medium">{v.name}</span>
                        <span className="block text-[12px] text-stone-500">{v.gender === "female" ? "Female" : "Male"}{v.tone ? ` · ${v.tone}` : ""}</span>
                    </span>
                    {v.sample_url && (
                        <button type="button" aria-label={`Play ${v.name}`}
                                onClick={(e) => { e.stopPropagation(); onPlay(v); }}
                                className="p-1.5 rounded text-stone-500 hover:text-plum hover:bg-white focus-visible:outline-2 focus-visible:outline-plum">
                            <Play size={13} />
                        </button>
                    )}
                    {v.id === value ? <Check size={14} className="text-plum shrink-0" aria-hidden /> : <span className="w-3.5 shrink-0" />}
                </div>
            )}
        />
    );
}

/** The language calls start in. */
export function LanguageMenu({ value, onChange }: { value: LanguageCode; onChange: (code: LanguageCode) => void }) {
    const options = LANGUAGES.map((l) => ({ id: l.code, label: l.label }));
    return (
        <Dropdown
            label="Language"
            width="w-56"
            value={value}
            options={options}
            onPick={(id) => onChange(id as LanguageCode)}
            button={<span className="font-medium">{LANGUAGES.find((l) => l.code === value)?.label ?? value}</span>}
            renderOption={(o, active) => (
                <div className={cn("mx-1 px-2.5 py-1.5 rounded-md flex items-center justify-between text-[13px]", active && "bg-stone-100")}>
                    {o.label}
                    {o.id === value && <Check size={14} className="text-plum" aria-hidden />}
                </div>
            )}
        />
    );
}

/** What a call minute costs, how quickly it answers, and how long its instructions are: the agent's summary line. */
export function AgentDetailsLine({ model, saved, details }: { model?: VoiceModel; saved: boolean; details?: AgentDetails | null }) {
    if (!model) return <Skeleton className="h-5 w-96" />;
    const measured = saved ? details?.reply_sec_measured ?? null : null;
    const expected = model.first_words_sec !== null ? Math.round((model.first_words_sec + REPLY_OVERHEAD_SEC) * 100) / 100 : null;
    const items: [string, string, string?][] = [
        ["Cost", `${formatRate(model.credits_per_minute)} credits a minute`],
        ["Replies in", measured !== null ? `${seconds(measured)}` : expected !== null ? `about ${seconds(expected)}` : "not measured yet",
         measured !== null ? `Median over its last ${details!.calls_measured} calls` : "Expected from the model's speed in our tests"],
        ["Instructions", details ? `about ${formatNumber(Math.round(details.prompt_tokens / 50) * 50)} tokens` : "…",
         "The opening, instructions and knowledge that go with every answer. Longer instructions answer a little slower."],
    ];
    return (
        <dl className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[13px]">
            {items.map(([label, value, hint]) => (
                <div key={label} className="flex items-baseline gap-1.5" title={hint}>
                    <dt className="text-stone-500">{label}</dt>
                    <dd className="font-medium tabular-nums">{value}</dd>
                </div>
            ))}
        </dl>
    );
}
