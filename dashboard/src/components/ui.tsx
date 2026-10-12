"use client";

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { X } from "lucide-react";
import {
    createContext, useCallback, useContext, useEffect, useId, useRef, useState,
    type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode,
    type Ref, type SelectHTMLAttributes, type TextareaHTMLAttributes,
} from "react";

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));

const focusRing = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum";

/* ---------- Button ---------- */

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: "primary" | "secondary" | "ghost" | "danger";
    size?: "sm" | "md";
};

export function Button({ variant = "secondary", size = "md", className, ...props }: ButtonProps) {
    return (
        <button
            {...props}
            className={cn(
                "inline-flex items-center justify-center gap-1.5 rounded-md font-medium whitespace-nowrap transition-colors disabled:opacity-50 disabled:pointer-events-none",
                focusRing,
                size === "sm" ? "h-8 px-3 text-[13px]" : "h-9 px-4 text-sm",
                variant === "primary" && "bg-plum text-white hover:bg-plum-hover",
                variant === "secondary" && "bg-white text-ink border border-line-strong hover:bg-stone-50",
                variant === "ghost" && "text-stone-600 hover:text-ink hover:bg-stone-100",
                variant === "danger" && "bg-white text-signal border border-line-strong hover:bg-red-50 hover:border-red-200",
                className,
            )}
        />
    );
}

/* ---------- Layout blocks ---------- */

export function Card({ className, children }: { className?: string; children: ReactNode }) {
    return <div className={cn("bg-white border border-line rounded-lg", className)}>{children}</div>;
}

export function SectionHeader({ title, description, action }: { title: string; description?: ReactNode; action?: ReactNode }) {
    return (
        <div className="flex items-start justify-between gap-4 mb-4">
            <div>
                <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
                {description && <p className="text-[13px] text-stone-500 mt-0.5 max-w-xl">{description}</p>}
            </div>
            {action}
        </div>
    );
}

/** A two-column settings row: label and help on the left, control on the right. */
export function SettingRow({ label, hint, htmlFor, children }: { label: string; hint?: ReactNode; htmlFor?: string; children: ReactNode }) {
    return (
        <div className="grid gap-3 py-5 border-t border-line first:border-t-0 md:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] md:gap-10">
            <div>
                <label htmlFor={htmlFor} className="text-sm font-medium text-ink">{label}</label>
                {hint && <p className="text-[13px] text-stone-500 mt-1 leading-relaxed">{hint}</p>}
            </div>
            <div className="min-w-0">{children}</div>
        </div>
    );
}

/* ---------- Form controls ---------- */

const control = "w-full bg-white border border-line-strong rounded-md text-sm text-ink placeholder:text-stone-400 hover:border-stone-400 focus:outline-none focus:border-plum focus:ring-2 focus:ring-plum/15 disabled:bg-stone-50 disabled:text-stone-500";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
    return <input {...props} className={cn(control, "h-9 px-3", className)} />;
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement> & { ref?: Ref<HTMLTextAreaElement> }) {
    return <textarea {...props} className={cn(control, "px-3 py-2 leading-relaxed resize-y min-h-20", className)} />;
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
    return (
        <select
            {...props}
            className={cn(control, "h-9 pl-3 pr-8 appearance-none bg-no-repeat bg-[right_0.6rem_center] bg-[length:12px]", className)}
            style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12' fill='none' stroke='%2378716c' stroke-width='1.5'%3E%3Cpath d='M3 4.5l3 3 3-3'/%3E%3C/svg%3E\")" }}
        >
            {children}
        </select>
    );
}

export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
    return (
        <button
            type="button"
            role="switch"
            aria-checked={checked}
            aria-label={label}
            disabled={disabled}
            onClick={() => onChange(!checked)}
            className={cn(
                "relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors disabled:opacity-50",
                focusRing,
                checked ? "bg-plum" : "bg-stone-300",
            )}
        >
            <span className={cn("absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform", checked && "translate-x-4")} />
        </button>
    );
}

export function Segmented<T extends string>({ value, onChange, options, label }: {
    value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; label: string;
}) {
    return (
        <div role="radiogroup" aria-label={label} className="inline-flex p-0.5 bg-stone-100 rounded-md">
            {options.map((o) => (
                <button
                    key={o.value}
                    type="button"
                    role="radio"
                    aria-checked={value === o.value}
                    onClick={() => onChange(o.value)}
                    className={cn(
                        "h-7 px-3 text-[13px] rounded-[5px] transition-colors",
                        focusRing,
                        value === o.value ? "bg-white text-ink font-medium shadow-[0_1px_2px_rgba(0,0,0,0.08)]" : "text-stone-500 hover:text-ink",
                    )}
                >
                    {o.label}
                </button>
            ))}
        </div>
    );
}

/** Free-text phrases, added with Enter or comma, removed individually. */
export function PhraseInput({ value, onChange, placeholder, label, keepCase = false }: {
    value: string[]; onChange: (v: string[]) => void; placeholder?: string; label: string; keepCase?: boolean;
}) {
    const [text, setText] = useState("");
    const add = () => {
        const p = keepCase ? text.trim() : text.trim().toLowerCase();
        if (p && !value.some((v) => v.toLowerCase() === p.toLowerCase())) onChange([...value, p]);
        setText("");
    };
    return (
        <div className={cn(control, "flex flex-wrap gap-1.5 p-1.5 h-auto focus-within:border-plum focus-within:ring-2 focus-within:ring-plum/15")}>
            {value.map((p) => (
                <span key={p} className="inline-flex items-center gap-1 h-6 pl-2 pr-1 rounded bg-stone-100 text-[13px] text-stone-700">
                    {p}
                    <button type="button" onClick={() => onChange(value.filter((x) => x !== p))} aria-label={`Remove "${p}"`} className="p-0.5 rounded text-stone-400 hover:text-ink">
                        <X size={12} />
                    </button>
                </span>
            ))}
            <input
                value={text}
                aria-label={label}
                placeholder={value.length ? "" : placeholder}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); }
                    if (e.key === "Backspace" && !text && value.length) onChange(value.slice(0, -1));
                }}
                onBlur={add}
                className="flex-1 min-w-32 h-6 px-1 text-sm bg-transparent outline-none placeholder:text-stone-400"
            />
        </div>
    );
}

/* ---------- Status ---------- */

const toneDot = { good: "bg-emerald-600", neutral: "bg-stone-400", warn: "bg-amber-500", bad: "bg-signal", plum: "bg-plum" } as const;

export function Status({ tone, children }: { tone: keyof typeof toneDot; children: ReactNode }) {
    return (
        <span className="inline-flex items-center gap-1.5 text-[13px] text-stone-700 whitespace-nowrap">
            <span className={cn("h-1.5 w-1.5 rounded-full", toneDot[tone])} aria-hidden />
            {children}
        </span>
    );
}

/** A quiet, page-level message (setup needed, something to know). */
export function Notice({ title, children, action, className }: { title: string; children?: ReactNode; action?: ReactNode; className?: string }) {
    return (
        <div className={cn("flex flex-col sm:flex-row sm:items-center gap-3 px-4 py-3 mb-6 border border-line-strong rounded-md bg-white", className)}>
            <div className="text-[13px] leading-relaxed">
                <span className="font-medium text-ink">{title}.</span>{" "}
                <span className="text-stone-600">{children}</span>
            </div>
            {action && <div className="sm:ml-auto shrink-0">{action}</div>}
        </div>
    );
}

export function Skeleton({ className }: { className?: string }) {
    return <div className={cn("animate-pulse rounded-md bg-stone-200/60", className)} />;
}

export function EmptyState({ title, body, action }: { title: string; body: ReactNode; action?: ReactNode }) {
    return (
        <div className="py-14 px-6 text-center">
            <p className="text-sm font-medium text-ink">{title}</p>
            <p className="text-[13px] text-stone-500 mt-1 max-w-sm mx-auto">{body}</p>
            {action && <div className="mt-5">{action}</div>}
        </div>
    );
}

/* ---------- Overlays ---------- */

function useEscape(open: boolean, onClose: () => void) {
    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
        document.addEventListener("keydown", onKey);
        const prev = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        return () => {
            document.removeEventListener("keydown", onKey);
            document.body.style.overflow = prev;
        };
    }, [open, onClose]);
}

export function Dialog({ open, onClose, title, description, children, footer }: {
    open: boolean; onClose: () => void; title: string; description?: ReactNode; children: ReactNode; footer?: ReactNode;
}) {
    const id = useId();
    const panel = useRef<HTMLDivElement>(null);
    useEscape(open, onClose);
    useEffect(() => {
        // Respect a field's autoFocus; otherwise move focus into the dialog.
        if (open && !panel.current?.contains(document.activeElement)) panel.current?.focus();
    }, [open]);
    if (!open) return null;
    return (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
            <div className="absolute inset-0 bg-ink/30" onClick={onClose} aria-hidden />
            <div
                ref={panel}
                tabIndex={-1}
                role="dialog"
                aria-modal="true"
                aria-labelledby={id}
                className="relative w-full sm:max-w-md bg-white rounded-t-lg sm:rounded-lg border border-line shadow-[0_16px_48px_rgba(28,23,25,0.18)] outline-none"
            >
                <div className="flex items-start justify-between gap-4 px-5 pt-5">
                    <div>
                        <h2 id={id} className="text-[15px] font-semibold text-ink">{title}</h2>
                        {description && <p className="text-[13px] text-stone-500 mt-1">{description}</p>}
                    </div>
                    <button onClick={onClose} aria-label="Close" className={cn("p-1 -m-1 rounded text-stone-400 hover:text-ink", focusRing)}>
                        <X size={16} />
                    </button>
                </div>
                <div className="px-5 py-4">{children}</div>
                {footer && <div className="flex justify-end gap-2 px-5 py-3 border-t border-line bg-stone-50/60 rounded-b-lg">{footer}</div>}
            </div>
        </div>
    );
}

export function Sheet({ open, onClose, title, subtitle, children }: {
    open: boolean; onClose: () => void; title: ReactNode; subtitle?: ReactNode; children: ReactNode;
}) {
    const id = useId();
    const panel = useRef<HTMLDivElement>(null);
    useEscape(open, onClose);
    useEffect(() => { if (open) panel.current?.focus(); }, [open]);
    if (!open) return null;
    return (
        <div className="fixed inset-0 z-50">
            <div className="absolute inset-0 bg-ink/20" onClick={onClose} aria-hidden />
            <div
                ref={panel}
                tabIndex={-1}
                role="dialog"
                aria-modal="true"
                aria-labelledby={id}
                className="absolute inset-y-0 right-0 w-full max-w-xl bg-white border-l border-line shadow-[-16px_0_48px_rgba(28,23,25,0.12)] flex flex-col outline-none"
            >
                <div className="flex items-start justify-between gap-4 px-6 py-4 border-b border-line">
                    <div className="min-w-0">
                        <h2 id={id} className="text-[15px] font-semibold text-ink truncate">{title}</h2>
                        {subtitle && <div className="text-[13px] text-stone-500 mt-0.5">{subtitle}</div>}
                    </div>
                    <button onClick={onClose} aria-label="Close" className={cn("p-1 -m-1 rounded text-stone-400 hover:text-ink", focusRing)}>
                        <X size={16} />
                    </button>
                </div>
                <div className="flex-1 overflow-y-auto">{children}</div>
            </div>
        </div>
    );
}

export function SaveBar({ visible, saving, onDiscard, onSave }: { visible: boolean; saving: boolean; onDiscard: () => void; onSave: () => void }) {
    if (!visible) return null;
    return (
        <div className="fixed bottom-4 inset-x-4 sm:inset-x-auto sm:left-1/2 sm:-translate-x-1/2 z-40 flex items-center gap-3 pl-4 pr-2 py-2 bg-white border border-line-strong rounded-lg shadow-[0_8px_30px_rgba(28,23,25,0.12)]">
            <span className="text-sm text-stone-600 mr-auto sm:mr-4">Unsaved changes</span>
            <Button size="sm" variant="ghost" onClick={onDiscard}>Discard</Button>
            <Button size="sm" variant="primary" onClick={onSave} disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
        </div>
    );
}

/* ---------- Toast ---------- */

const ToastContext = createContext<(message: string) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
    const [message, setMessage] = useState<string | null>(null);
    const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
    const show = useCallback((m: string) => {
        setMessage(m);
        clearTimeout(timer.current);
        timer.current = setTimeout(() => setMessage(null), 3600);
    }, []);
    return (
        <ToastContext.Provider value={show}>
            {children}
            <div aria-live="polite" className="fixed bottom-5 left-1/2 -translate-x-1/2 z-[60] px-4 w-full max-w-md pointer-events-none">
                {message && (
                    <div className="pointer-events-auto mx-auto w-fit max-w-full px-4 py-2.5 rounded-md bg-ink text-white text-[13px] shadow-lg">
                        {message}
                    </div>
                )}
            </div>
        </ToastContext.Provider>
    );
}

export const useToast = () => useContext(ToastContext);
