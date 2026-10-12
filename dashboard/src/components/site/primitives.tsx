import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";
import { cn } from "./cn";

/** Shared building blocks for the marketing site. Same tokens as the product (plum, paper, line, ink). */

export function Container({ className, children }: { className?: string; children: ReactNode }) {
    return <div className={cn("max-w-6xl mx-auto px-4 sm:px-6", className)}>{children}</div>;
}

export function Section({ id, className, children, tone = "paper" }: {
    id?: string; className?: string; children: ReactNode; tone?: "paper" | "white" | "dark";
}) {
    return (
        <section id={id} className={cn(
            "scroll-mt-16 py-20 sm:py-28",
            tone === "white" && "bg-white border-y border-line",
            tone === "dark" && "bg-aubergine text-white",
            className,
        )}>
            {children}
        </section>
    );
}

export function Eyebrow({ children, dark }: { children: ReactNode; dark?: boolean }) {
    return <p data-reveal className={cn("text-[13px] font-medium mb-3", dark ? "text-[#d9b8e0]" : "text-plum")}>{children}</p>;
}

export function Heading({ children, className }: { children: ReactNode; className?: string }) {
    return <h2 data-reveal style={{ "--reveal-delay": "60ms" } as CSSProperties}
               className={cn("font-display text-[30px] sm:text-[44px] leading-[1.06] font-medium tracking-[-0.02em] max-w-2xl text-balance", className)}>{children}</h2>;
}

export function Lead({ children, dark, className }: { children: ReactNode; dark?: boolean; className?: string }) {
    return <p data-reveal style={{ "--reveal-delay": "120ms" } as CSSProperties}
              className={cn("text-[17px] leading-relaxed mt-4 max-w-2xl", dark ? "text-white/70" : "text-stone-600", className)}>{children}</p>;
}

export function PrimaryLink({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
    return (
        <Link href={href} className={cn(
            "inline-flex items-center justify-center gap-2 h-11 px-5 rounded-md bg-plum text-white text-[15px] font-medium",
            "hover:bg-plum-hover transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum",
            className,
        )}>{children}</Link>
    );
}

export function SecondaryLink({ href, children, dark, className }: { href: string; children: ReactNode; dark?: boolean; className?: string }) {
    return (
        <Link href={href} className={cn(
            "inline-flex items-center justify-center gap-2 h-11 px-5 rounded-md text-[15px] font-medium border transition-colors",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum",
            dark ? "border-white/25 text-white hover:bg-white/10" : "border-line-strong bg-white text-ink hover:bg-stone-50",
            className,
        )}>{children}</Link>
    );
}

/** A status dot with a label, matching the product's Status component. */
export function Dot({ tone, children }: { tone: "good" | "warn" | "plum" | "neutral" | "bad"; children: ReactNode }) {
    const color = { good: "bg-emerald-600", warn: "bg-amber-500", plum: "bg-plum", neutral: "bg-stone-400", bad: "bg-signal" }[tone];
    return (
        <span className="inline-flex items-center gap-1.5 text-[12px] text-stone-700 whitespace-nowrap">
            <span className={cn("h-1.5 w-1.5 rounded-full", color)} aria-hidden />{children}
        </span>
    );
}

/** A window-like frame for product previews. */
export function Frame({ title, meta, children, className }: { title: ReactNode; meta?: ReactNode; children: ReactNode; className?: string }) {
    return (
        <div data-reveal className={cn("bg-white rounded-lg border border-line shadow-[0_1px_2px_rgba(28,23,25,0.04),0_12px_32px_-12px_rgba(28,23,25,0.18)] overflow-hidden text-ink", className)}>
            <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-line bg-stone-50/70">
                <span className="text-[12px] font-medium truncate">{title}</span>
                {meta && <span className="text-[11px] text-stone-500 shrink-0">{meta}</span>}
            </div>
            {children}
        </div>
    );
}
