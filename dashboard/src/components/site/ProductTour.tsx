"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Lock } from "lucide-react";
import { cn } from "./cn";

/*
 * Real product screenshots (from a demo workspace with sample data), one feature at a time.
 * Advances when the progress line fills; pauses on hover, on focus and when off screen.
 * With reduced motion there is no auto-advance or slide movement.
 */

const SLIDES = [
    {
        id: "agent", title: "Set up an assistant in minutes", path: "voice/agents",
        text: "Pick a language and a natural voice, choose what it should find out, and test it in your browser or on your own phone.",
        alt: "The agent settings page with language, voice choices and test call panel",
    },
    {
        id: "call", title: "Every call, written down", path: "voice/calls",
        text: "A recording, transcript and short summary for each call, with the details collected, whether it met its goal and how the caller felt.",
        alt: "A call opened in the Calls page, showing its summary, collected details and transcript",
    },
    {
        id: "contacts", title: "Remembers every caller", path: "voice/contacts",
        text: "Each caller's name, what they told the assistant, your team's notes and every call, with their lead rating and what's coming up for them.",
        alt: "A contact opened in Contacts, with the lead rating, an upcoming meeting, team notes and what they told the assistant",
    },
    {
        id: "campaign", title: "Call a whole list", path: "voice/campaigns",
        text: "Upload the people who asked to hear from you. Watch progress as it happens, and export who booked, who didn't and why.",
        alt: "A campaign page with progress, reached and goal-met counts, and results for each person",
    },
    {
        id: "schedule", title: "Follow-ups and meetings", path: "voice/schedule",
        text: "Call-backs people asked for, follow-ups by lead rating and meeting requests waiting for your OK, all in one place.",
        alt: "The Schedule page with the month's call-backs, follow-ups and meetings, and meeting requests waiting for approval",
    },
    {
        id: "data", title: "Every lead in one table", path: "voice/data",
        text: "The details from each conversation, scored hot, warm or cold, ready to export or send to your CRM.",
        alt: "The Collected data table with lead scores, outcomes and the fields each call collected",
    },
    {
        id: "livechat", title: "Your team steps in on time", path: "live-chat",
        text: "Website and WhatsApp conversations that need a person land in one inbox, with internal notes and saved replies.",
        alt: "Live chat with a WhatsApp conversation, a team-only note and the reply box",
    },
    {
        id: "questions", title: "Better every week", path: "questions",
        text: "Questions it couldn't answer are grouped and counted. Answer one once and the assistant uses it from then on.",
        alt: "The Questions page listing unanswered questions with how often each was asked",
    },
];
const SECONDS = 6;

export default function ProductTour() {
    const [active, setActive] = useState(0);
    const [hovered, setHovered] = useState(false);
    const [focused, setFocused] = useState(false);
    const [visible, setVisible] = useState(false);
    // Only the current and next screenshots load at first; the rest follow once the tour has been seen.
    const [warm, setWarm] = useState(false);
    const root = useRef<HTMLDivElement>(null);
    const list = useRef<HTMLDivElement>(null);
    const tabs = useRef<(HTMLButtonElement | null)[]>([]);
    const paused = hovered || focused || !visible;

    useEffect(() => {
        const el = root.current;
        if (!el || !("IntersectionObserver" in window)) return setVisible(true);
        const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: 0.35 });
        io.observe(el);
        return () => io.disconnect();
    }, []);

    useEffect(() => {
        if (!visible || warm) return;
        const t = setTimeout(() => setWarm(true), 1200);
        return () => clearTimeout(t);
    }, [visible, warm]);

    // On small screens the features are a row of chips; keep the active one in view (without moving the page).
    useEffect(() => {
        const row = list.current, tab = tabs.current[active];
        if (!row || !tab || row.scrollWidth <= row.clientWidth) return;
        const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        row.scrollTo({ left: tab.offsetLeft - (row.clientWidth - tab.offsetWidth) / 2, behavior: smooth ? "smooth" : "auto" });
    }, [active]);

    const go = (i: number, focus = false) => {
        const next = (i + SLIDES.length) % SLIDES.length;
        setActive(next);
        if (focus) tabs.current[next]?.focus();
    };
    const onKey = (e: KeyboardEvent) => {
        const forward = e.key === "ArrowDown" || e.key === "ArrowRight";
        const back = e.key === "ArrowUp" || e.key === "ArrowLeft";
        if (forward || back) { e.preventDefault(); go(active + (forward ? 1 : -1), true); }
    };
    const slide = SLIDES[active];

    return (
        <div ref={root} onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
             onFocus={() => setFocused(true)} onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setFocused(false); }}
             className="mt-12 grid lg:grid-cols-[19rem_minmax(0,1fr)] gap-6 lg:gap-12 items-start">
            {/* Feature list: chips on small screens, a list with descriptions on large ones. */}
            <div ref={list} role="tablist" aria-label="Product features" onKeyDown={onKey}
                 className="relative flex lg:flex-col gap-2 lg:gap-1 overflow-x-auto lg:overflow-visible -mx-4 px-4 lg:mx-0 lg:px-0 pb-1 [scrollbar-width:none]">
                {SLIDES.map((s, i) => {
                    const on = i === active;
                    return (
                        <button
                            key={s.id}
                            ref={(el) => { tabs.current[i] = el; }}
                            role="tab"
                            id={`tour-tab-${s.id}`}
                            aria-selected={on}
                            aria-controls="tour-panel"
                            tabIndex={on ? 0 : -1}
                            onClick={() => go(i)}
                            className={cn(
                                "relative shrink-0 text-left rounded-xl transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum",
                                "px-4 py-2.5 lg:px-5 lg:py-4 border",
                                on ? "bg-white border-line shadow-[0_1px_2px_rgba(28,23,25,0.05)]" : "border-transparent hover:bg-white/60",
                            )}
                        >
                            <span className={cn("block font-display text-[15px] lg:text-[17px] font-medium whitespace-nowrap lg:whitespace-normal",
                                                on ? "text-ink" : "text-stone-500")}>{s.title}</span>
                            <span className={cn("hidden lg:grid transition-[grid-template-rows,opacity] duration-500",
                                                on ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0")}>
                                <span className="overflow-hidden text-[14px] leading-relaxed text-stone-600 pt-1.5">{s.text}</span>
                            </span>
                            {on && (
                                <span className="absolute left-4 right-4 lg:left-5 lg:right-5 bottom-1 lg:bottom-2 h-[2px] rounded-full bg-line overflow-hidden" aria-hidden>
                                    <span key={active} className="tour-progress block h-full bg-plum"
                                          style={{ animationDuration: `${SECONDS}s`, animationPlayState: paused ? "paused" : "running" }}
                                          onAnimationEnd={() => go(active + 1)} />
                                </span>
                            )}
                        </button>
                    );
                })}
            </div>

            {/* On wide screens the monitor runs past the text column into the right margin, so the screens read larger. */}
            <div className="lg:-mr-[clamp(0px,(100vw_-_72rem)/2_-_1rem,12rem)]">
                <div id="tour-panel" role="tabpanel" aria-labelledby={`tour-tab-${slide.id}`}>
                    <Monitor path={slide.path}>
                        {SLIDES.map((s, i) => (
                            <div key={s.id} aria-hidden={i !== active}
                                 className={cn("absolute inset-0 transition-[opacity,transform] duration-700 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none",
                                               i === active ? "opacity-100 translate-x-0 scale-100" : "opacity-0 translate-x-6 scale-[0.985]")}>
                                {/* Captured at 2x and stored as lossless WebP, so small UI text stays crisp. Plain <img> rather
                                    than next/image: the optimizer would re-encode them lossy. Desktop always gets the 2400px
                                    file so the screens stay sharp when zoomed; phones get the 1200px one. */}
                                {(warm || i === active || i === (active + 1) % SLIDES.length) && (
                                    <img src={`/screens/${s.id}.webp`} srcSet={`/screens/${s.id}-1200.webp 1200w, /screens/${s.id}.webp 2400w`}
                                         sizes="(min-width: 1024px) 2400px, 100vw" width={2400} height={1500} alt={s.alt}
                                         loading="lazy" decoding="async" className="absolute inset-0 h-full w-full object-cover object-top" />
                                )}
                            </div>
                        ))}
                    </Monitor>
                </div>
                {/* On small screens the description sits under the screenshot. */}
                <p className="lg:hidden text-[15px] leading-relaxed text-stone-600 mt-4">{slide.text}</p>
                <p className="text-[12px] text-stone-400 mt-3">Screens from a demo workspace with sample data.</p>
            </div>
        </div>
    );
}

/**
 * A desktop display drawn in CSS: aluminium edge, black bezel with a camera, a browser window
 * on screen, and a stand that casts a soft shadow on the "desk". Scales with its container.
 */
function Monitor({ path, children }: { path: string; children: ReactNode }) {
    return (
        <div className="relative pb-3">
            {/* Display: thin aluminium edge around a black bezel. */}
            <div className={cn(
                "relative rounded-[13px] sm:rounded-[20px] p-[1.5px] bg-[linear-gradient(180deg,#e2dfe4_0%,#a8a4ad_55%,#8a8690_100%)]",
                "shadow-[0_2px_4px_rgba(28,23,25,0.10),0_22px_40px_-16px_rgba(28,23,25,0.38),0_60px_100px_-36px_rgba(46,0,55,0.50)]",
            )}>
                <div className="relative rounded-[11.5px] sm:rounded-[18.5px] bg-[linear-gradient(180deg,#1d1a20_0%,#0d0b0f_100%)] p-[6px] sm:p-[11px] shadow-[inset_0_1px_0_rgba(255,255,255,0.10),inset_0_0_0_1px_rgba(0,0,0,0.6)]">
                    <span aria-hidden className="absolute left-1/2 -translate-x-1/2 top-[2px] sm:top-[4px] h-[3px] w-[3px] sm:h-1 sm:w-1 rounded-full bg-[#2c2932] shadow-[0_0_0_1px_rgba(0,0,0,0.7)]" />
                    <div className="relative overflow-hidden rounded-[4px] sm:rounded-[7px] bg-white">
                        {/* Browser window chrome. */}
                        <div className="flex items-center h-6 sm:h-8 px-2.5 sm:px-3.5 bg-[#f2f0f3] border-b border-black/[0.06]">
                            <span className="flex gap-1 sm:gap-1.5 w-10 sm:w-14" aria-hidden>
                                <i className="block h-[6px] w-[6px] sm:h-2.5 sm:w-2.5 rounded-full bg-[#ec6a5e]" />
                                <i className="block h-[6px] w-[6px] sm:h-2.5 sm:w-2.5 rounded-full bg-[#f4bf4f]" />
                                <i className="block h-[6px] w-[6px] sm:h-2.5 sm:w-2.5 rounded-full bg-[#61c554]" />
                            </span>
                            <span className="mx-auto flex items-center justify-center gap-1 h-4 sm:h-5 w-[58%] rounded-[5px] bg-white border border-black/[0.06] text-[8.5px] sm:text-[11px] text-stone-500 truncate">
                                <Lock className="h-2 w-2 sm:h-2.5 sm:w-2.5 shrink-0" aria-hidden />
                                <span className="truncate">nimmiai.in/dashboard/{path}</span>
                            </span>
                            <span className="w-10 sm:w-14" aria-hidden />
                        </div>
                        <div className="relative bg-paper" style={{ aspectRatio: "16 / 10" }}>{children}</div>
                    </div>
                </div>
            </div>

            {/* Stand: neck (shaded where the display meets it) and foot. */}
            <div aria-hidden className="relative mx-auto w-[16%] aspect-[2/1] [clip-path:polygon(5%_0,95%_0,100%_100%,0_100%)]
                 bg-[linear-gradient(90deg,#9c98a1_0%,#d6d3d9_16%,#efedf0_50%,#d1ced4_84%,#97939c_100%)]">
                <span className="absolute inset-0 bg-[linear-gradient(180deg,rgba(20,16,22,0.45)_0%,rgba(20,16,22,0.08)_35%,transparent_60%)]" />
            </div>
            <div aria-hidden className="relative mx-auto w-[38%] aspect-[32/1] rounded-[2px_2px_8px_8px/2px_2px_5px_5px]
                 bg-[linear-gradient(180deg,#f6f4f7_0%,#d9d6dc_45%,#a7a3ac_100%)] shadow-[0_6px_10px_-4px_rgba(28,23,25,0.40)]" />
            {/* Contact shadow on the surface below. */}
            <div aria-hidden className="absolute left-1/2 -translate-x-1/2 bottom-0 w-[58%] h-5 sm:h-7 rounded-[50%] blur-md bg-[radial-gradient(closest-side,rgba(46,0,55,0.30),rgba(46,0,55,0))]" />
        </div>
    );
}
