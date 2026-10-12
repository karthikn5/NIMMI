"use client";

import { useEffect, useId, useState, type ReactNode } from "react";
import { cn } from "@/components/ui";
import { contrast, isHex } from "@/lib/color";

/** Builder form building blocks: quiet sections, labelled fields, colour and range inputs. */

export function Section({ title, description, children, action }: { title: string; description?: ReactNode; children: ReactNode; action?: ReactNode }) {
    return (
        <section className="py-6 border-t border-line first:border-t-0 first:pt-1">
            <div className="flex items-start justify-between gap-4 mb-4">
                <div>
                    <h3 className="text-sm font-semibold text-ink">{title}</h3>
                    {description && <p className="text-[13px] text-stone-500 mt-0.5 leading-relaxed">{description}</p>}
                </div>
                {action}
            </div>
            <div className="space-y-4">{children}</div>
        </section>
    );
}

export function Field({ label, hint, htmlFor, children, aside }: { label: string; hint?: ReactNode; htmlFor?: string; children: ReactNode; aside?: ReactNode }) {
    return (
        <div>
            <div className="flex items-baseline justify-between gap-3 mb-1.5">
                <label htmlFor={htmlFor} className="text-[13px] font-medium text-stone-700">{label}</label>
                {aside && <span className="text-[12px] text-stone-500 tabular-nums">{aside}</span>}
            </div>
            {children}
            {hint && <p className="text-[12px] text-stone-500 mt-1.5 leading-relaxed">{hint}</p>}
        </div>
    );
}

/** Switch with its label on the left, for on/off settings. */
export function ToggleRow({ label, hint, checked, onChange }: { label: string; hint?: ReactNode; checked: boolean; onChange: (v: boolean) => void }) {
    const id = useId();
    return (
        <div className="flex items-start justify-between gap-4">
            <div>
                <label htmlFor={id} className="text-[13px] font-medium text-stone-700 cursor-pointer">{label}</label>
                {hint && <p className="text-[12px] text-stone-500 mt-0.5 leading-relaxed">{hint}</p>}
            </div>
            <button
                id={id}
                type="button"
                role="switch"
                aria-checked={checked}
                onClick={() => onChange(!checked)}
                className={cn("relative mt-0.5 inline-flex h-5 w-9 shrink-0 rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum",
                              checked ? "bg-plum" : "bg-stone-300")}
            >
                <span className={cn("absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform", checked && "translate-x-4")} />
            </button>
        </div>
    );
}

/** A swatch that opens the native picker, plus an editable hex value. */
export function ColorField({ label, value, onChange, against, hint, placeholder, onClear }: {
    label: string; value: string; onChange: (v: string) => void;
    /** When set, shows whether text in this colour reads on that background (or the reverse). */
    against?: string;
    hint?: ReactNode;
    placeholder?: string;
    onClear?: () => void;
}) {
    const id = useId();
    const [text, setText] = useState(value);
    useEffect(() => setText(value), [value]);
    const ratio = against && isHex(value) && isHex(against) ? contrast(value, against) : null;
    return (
        <div>
            <label htmlFor={id} className="block text-[13px] font-medium text-stone-700 mb-1.5">{label}</label>
            <div className="flex items-center h-9 rounded-md border border-line-strong bg-white hover:border-stone-400 focus-within:border-plum focus-within:ring-2 focus-within:ring-plum/15">
                <span className="relative ml-1.5 h-6 w-6 shrink-0 rounded border border-black/10 overflow-hidden"
                      style={{ background: value || "repeating-conic-gradient(#e7e5e4 0% 25%, #fff 0% 50%) 50% / 8px 8px" }}>
                    <input type="color" aria-label={`${label}: pick a colour`} value={isHex(value) ? value : "#ffffff"}
                           onChange={(e) => onChange(e.target.value)}
                           className="absolute inset-0 h-full w-full opacity-0 cursor-pointer" />
                </span>
                <input
                    id={id}
                    value={text}
                    placeholder={placeholder}
                    spellCheck={false}
                    onChange={(e) => {
                        const v = e.target.value.trim();
                        setText(v);
                        const hex = v.startsWith("#") ? v : `#${v}`;
                        if (isHex(hex)) onChange(hex.toLowerCase());
                    }}
                    onBlur={() => setText(value)}
                    className="min-w-0 flex-1 h-full px-2 text-[13px] font-mono uppercase text-ink bg-transparent outline-none placeholder:normal-case placeholder:font-sans placeholder:text-stone-400"
                />
                {onClear && value && (
                    <button type="button" onClick={onClear} className="mr-1.5 px-1.5 h-6 rounded text-[12px] text-stone-500 hover:text-ink hover:bg-stone-100">
                        Reset
                    </button>
                )}
            </div>
            {ratio !== null ? (
                <p className={cn("text-[12px] mt-1.5", ratio >= 4.5 ? "text-stone-500" : "text-amber-700")}>
                    Contrast {ratio.toFixed(1)}:1{ratio >= 4.5 ? " · easy to read" : " · may be hard to read"}
                </p>
            ) : hint && <p className="text-[12px] text-stone-500 mt-1.5">{hint}</p>}
        </div>
    );
}

export function RangeField({ label, value, onChange, min, max, step = 1, unit = "px", format }: {
    label: string; value: number; onChange: (v: number) => void; min: number; max: number; step?: number; unit?: string;
    format?: (v: number) => string;
}) {
    const id = useId();
    const pct = ((value - min) / (max - min)) * 100;
    return (
        <Field label={label} htmlFor={id} aside={format ? format(value) : `${value}${unit}`}>
            <input
                id={id}
                type="range"
                min={min}
                max={max}
                step={step}
                value={value}
                onChange={(e) => onChange(Number(e.target.value))}
                className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-plum focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-plum"
                style={{ background: `linear-gradient(to right, var(--color-plum) ${pct}%, #e7e5e4 ${pct}%)` }}
            />
        </Field>
    );
}

/** A row of equal choices shown as small cards (shapes, sides). */
export function ChoiceRow<T extends string>({ label, value, onChange, options }: {
    label: string; value: T; onChange: (v: T) => void; options: { value: T; label: string; icon?: ReactNode }[];
}) {
    return (
        <div>
            <p className="text-[13px] font-medium text-stone-700 mb-1.5">{label}</p>
            <div role="radiogroup" aria-label={label} className="grid gap-2" style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}>
                {options.map((o) => (
                    <button
                        key={o.value}
                        type="button"
                        role="radio"
                        aria-checked={value === o.value}
                        onClick={() => onChange(o.value)}
                        className={cn(
                            "flex flex-col items-center justify-center gap-1.5 h-16 rounded-md border text-[12px] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum",
                            value === o.value ? "border-plum bg-plum-tint text-ink" : "border-line-strong bg-white text-stone-600 hover:border-stone-400",
                        )}
                    >
                        {o.icon}
                        {o.label}
                    </button>
                ))}
            </div>
        </div>
    );
}
