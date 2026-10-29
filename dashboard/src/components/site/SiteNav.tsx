"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { Menu, X } from "lucide-react";
import { cn } from "./cn";

const LINKS = [
    { href: "/#product", label: "Product" },
    { href: "/#voice", label: "Voice" },
    { href: "/#industries", label: "Industries" },
    { href: "/pricing", label: "Pricing" },
    { href: "/blog", label: "Blog" },
];

const EASE = "duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none";

/**
 * Full-width bar at the top of the page. Once the page scrolls it condenses into a
 * floating frosted-glass pill with just the logo and the two actions.
 */
export default function SiteNav() {
    const [open, setOpen] = useState(false);
    const [compact, setCompact] = useState(false);

    useEffect(() => {
        const onScroll = () => setCompact(window.scrollY > 24);
        onScroll();
        window.addEventListener("scroll", onScroll, { passive: true });
        return () => window.removeEventListener("scroll", onScroll);
    }, []);

    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [open]);

    return (
        <header className={cn("fixed inset-x-0 top-0 z-50 flex flex-col items-center transition-[padding]", EASE, compact ? "pt-3" : "pt-0")}>
            <nav
                aria-label="Main"
                className={cn(
                    "flex items-center border transition-[max-width,width,height,padding,border-radius,background-color,box-shadow,border-color]",
                    EASE,
                    compact
                        ? "w-[calc(100%-1.5rem)] max-w-[30rem] h-14 pl-4 pr-2 rounded-full bg-white/80 backdrop-blur-xl backdrop-saturate-150 border-white/70 shadow-[0_10px_30px_-12px_rgba(46,0,55,0.28),inset_0_1px_0_rgba(255,255,255,0.6)]"
                        : cn("w-full max-w-6xl h-16 px-4 sm:px-6 rounded-none border-transparent shadow-none", open ? "bg-paper" : "bg-transparent"),
                )}
            >
                <Link href="/" className="flex items-center gap-2 shrink-0 rounded focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-plum">
                    <Image src="/favicon.png" alt="" width={28} height={28} priority />
                    <span className="text-[16px] font-semibold text-plum tracking-tight">Nimmi AI</span>
                </Link>

                {/* Links fold away in the compact pill (and leave the tab order). */}
                <ul inert={compact} aria-hidden={compact}
                    className={cn("hidden md:flex items-center gap-7 overflow-hidden whitespace-nowrap transition-[max-width,opacity,margin]", EASE,
                                  compact ? "max-w-0 opacity-0 mx-0" : "max-w-[36rem] opacity-100 mx-auto")}>
                    {LINKS.map((l) => (
                        <li key={l.href}><Link href={l.href} className="text-[14px] text-stone-600 hover:text-ink transition-colors">{l.label}</Link></li>
                    ))}
                </ul>

                <div className="hidden md:flex items-center gap-1.5 ml-auto">
                    <Link href="/auth/login" className="h-10 px-4 inline-flex items-center rounded-full text-[14px] text-stone-700 hover:text-ink hover:bg-white/70 transition-colors">
                        Sign in
                    </Link>
                    <Link href="/auth/signup" className="h-10 px-5 inline-flex items-center rounded-full bg-plum text-white text-[14px] font-medium hover:bg-plum-hover transition-colors">
                        Start free
                    </Link>
                </div>

                <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="mobile-menu"
                        aria-label={open ? "Close menu" : "Open menu"}
                        className="md:hidden ml-auto h-10 w-10 inline-flex items-center justify-center rounded-full text-ink hover:bg-white/60">
                    {open ? <X size={21} /> : <Menu size={21} />}
                </button>
            </nav>

            {open && (
                <div id="mobile-menu" className={cn(
                    "md:hidden w-[calc(100%-1.5rem)] mt-2 rounded-2xl border border-white/70 bg-white/95 backdrop-blur-xl backdrop-saturate-150",
                    "shadow-[0_16px_40px_-16px_rgba(46,0,55,0.3)] overflow-hidden",
                )}>
                    <ul className="px-4 py-2">
                        {LINKS.map((l) => (
                            <li key={l.href}>
                                <Link href={l.href} onClick={() => setOpen(false)} className="block py-3 text-[16px] text-ink border-b border-line last:border-b-0">{l.label}</Link>
                            </li>
                        ))}
                    </ul>
                    <div className="px-4 pb-4 pt-1 grid grid-cols-2 gap-2.5">
                        <Link href="/auth/login" onClick={() => setOpen(false)} className="h-11 inline-flex items-center justify-center rounded-full border border-line-strong bg-white text-[15px]">Sign in</Link>
                        <Link href="/auth/signup" onClick={() => setOpen(false)} className="h-11 inline-flex items-center justify-center rounded-full bg-plum text-white text-[15px] font-medium">Start free</Link>
                    </div>
                </div>
            )}
        </header>
    );
}
