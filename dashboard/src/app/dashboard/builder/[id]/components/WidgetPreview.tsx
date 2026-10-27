"use client";

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Bot, Send, X } from "lucide-react";
import { isLight } from "@/lib/color";
import { assetUrl, type Visual } from "./design";

/**
 * The chat widget as visitors see it, drawn at real size inside a desktop or phone frame and scaled to fit.
 * Mirrors app/widget/[botId]/page.tsx (the chat) and backend/static/nimmi-widget.js (launcher, greeting, window).
 */

const DESKTOP = { w: 1280, h: 800, chrome: 40 };
const PHONE = { w: 390, h: 800 };

function useFit(w: number, h: number) {
    const ref = useRef<HTMLDivElement>(null);
    const [scale, setScale] = useState(0.5);
    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        const fit = () => setScale(Math.min(el.clientWidth / w, el.clientHeight / h, 1));
        fit();
        const ro = new ResizeObserver(fit);
        ro.observe(el);
        return () => ro.disconnect();
    }, [w, h]);
    return { ref, scale };
}

export default function WidgetPreview({ visual, botName, device, open, callbacks }: {
    visual: Visual; botName: string; device: "desktop" | "mobile"; open: boolean; callbacks: boolean;
}) {
    const size = device === "desktop" ? { w: DESKTOP.w, h: DESKTOP.h } : PHONE;
    const { ref, scale } = useFit(size.w, size.h);
    return (
        <div ref={ref} className="relative h-full w-full flex items-center justify-center">
            <div style={{ width: size.w * scale, height: size.h * scale }} className="relative">
                <div className="absolute top-0 left-0 origin-top-left" style={{ width: size.w, height: size.h, transform: `scale(${scale})` }}>
                    {device === "desktop"
                        ? <DesktopFrame visual={visual} botName={botName} open={open} callbacks={callbacks} />
                        : <PhoneFrame visual={visual} botName={botName} open={open} callbacks={callbacks} />}
                </div>
            </div>
        </div>
    );
}

/* ---------- Frames ---------- */

function DesktopFrame({ visual: v, botName, open, callbacks }: { visual: Visual; botName: string; open: boolean; callbacks: boolean }) {
    const viewportH = DESKTOP.h - DESKTOP.chrome;
    return (
        <div className="h-full w-full rounded-xl overflow-hidden bg-white border border-line shadow-[0_1px_2px_rgba(28,23,25,0.06),0_24px_60px_-24px_rgba(28,23,25,0.25)] flex flex-col">
            <div className="h-10 shrink-0 flex items-center gap-2 px-4 bg-stone-100 border-b border-line">
                <span className="h-3 w-3 rounded-full bg-[#ec6a5e]" /><span className="h-3 w-3 rounded-full bg-[#f4bf4f]" /><span className="h-3 w-3 rounded-full bg-[#61c554]" />
                <span className="mx-auto h-6 w-[38%] rounded-md bg-white border border-line text-[12px] text-stone-400 flex items-center justify-center">yourwebsite.com</span>
            </div>
            <div className="relative flex-1 overflow-hidden" style={{ height: viewportH }}>
                <SiteSkeleton />
                <Overlay visual={v} botName={botName} open={open} callbacks={callbacks} viewportH={viewportH} mobile={false} />
            </div>
        </div>
    );
}

function PhoneFrame({ visual: v, botName, open, callbacks }: { visual: Visual; botName: string; open: boolean; callbacks: boolean }) {
    const viewportH = PHONE.h - 24 - 44; // bezel and status bar
    return (
        <div className="h-full w-full rounded-[48px] bg-[#111] p-3 shadow-[0_24px_60px_-20px_rgba(28,23,25,0.45)]">
            <div className="h-full w-full rounded-[38px] overflow-hidden bg-white flex flex-col">
                <div className="h-11 shrink-0 flex items-center justify-between px-7 text-[13px] font-semibold text-ink">
                    <span>9:41</span>
                    <span className="h-6 w-24 rounded-full bg-[#111]" aria-hidden />
                    <span className="flex gap-1 items-center" aria-hidden><span className="h-2.5 w-4 rounded-sm border border-ink" /></span>
                </div>
                <div className="relative flex-1 overflow-hidden" style={{ height: viewportH }}>
                    <SiteSkeleton compact />
                    <Overlay visual={v} botName={botName} open={open} callbacks={callbacks} viewportH={viewportH} mobile />
                </div>
            </div>
        </div>
    );
}

function SiteSkeleton({ compact }: { compact?: boolean }) {
    const bar = "rounded-md bg-stone-200/70";
    return (
        <div className={compact ? "p-5 space-y-4" : "p-12 space-y-6"} aria-hidden>
            <div className="flex items-center justify-between">
                <div className={`${bar} h-6 w-28`} />
                {!compact && <div className="flex gap-6">{[0, 1, 2, 3].map((i) => <div key={i} className={`${bar} h-3 w-16`} />)}</div>}
            </div>
            <div className={compact ? "pt-6 space-y-3" : "pt-16 space-y-4 max-w-xl"}>
                <div className={`${bar} ${compact ? "h-7 w-4/5" : "h-10 w-full"}`} />
                <div className={`${bar} ${compact ? "h-7 w-3/5" : "h-10 w-4/5"}`} />
                <div className="space-y-2 pt-2">
                    <div className={`${bar} h-3 w-full`} /><div className={`${bar} h-3 w-11/12`} /><div className={`${bar} h-3 w-2/3`} />
                </div>
                <div className={`${compact ? "h-10 w-32" : "h-11 w-40"} rounded-md bg-stone-300/70 mt-4`} />
            </div>
            {!compact && <div className="grid grid-cols-3 gap-6 pt-10">{[0, 1, 2].map((i) => <div key={i} className={`${bar} h-36`} />)}</div>}
        </div>
    );
}

/* ---------- Launcher, greeting and chat window (positions as in nimmi-widget.js) ---------- */

function Overlay({ visual: v, botName, open, callbacks, viewportH, mobile }: {
    visual: Visual; botName: string; open: boolean; callbacks: boolean; viewportH: number; mobile: boolean;
}) {
    const side: CSSProperties = v.position === "left" ? { left: v.right_padding } : { right: v.right_padding };
    const windowStyle: CSSProperties = mobile
        ? { left: 20, right: 20, bottom: 90, height: viewportH - 120 }
        : { ...side, bottom: v.bottom_padding + 76, width: v.window_width, height: Math.min(v.window_height, viewportH - v.bottom_padding - 96) };
    return (
        <>
            {open ? (
                <div className="absolute flex flex-col overflow-hidden border border-black/5 shadow-[0_10px_40px_rgba(0,0,0,0.15)] bg-white"
                     style={{ ...windowStyle, borderRadius: v.border_radius }}>
                    <ChatWindow visual={v} botName={botName} callbacks={callbacks} />
                </div>
            ) : v.launcher_greeting.trim() ? (
                <div className="absolute max-w-[260px] pl-3.5 pr-9 py-3 bg-white text-[#1c1917] text-[14px] leading-[1.45] rounded-[14px] border border-black/5 shadow-[0_8px_28px_rgba(0,0,0,0.14)]"
                     style={{ ...side, bottom: v.bottom_padding + 76, fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif" }}>
                    {v.launcher_greeting}
                    <span className="absolute top-1.5 right-1.5 h-6 w-6 flex items-center justify-center text-stone-500 text-lg leading-none">×</span>
                </div>
            ) : null}
            <div className="absolute" style={{ ...side, bottom: v.bottom_padding }}>
                <Launcher visual={v} />
            </div>
        </>
    );
}

export function Launcher({ visual: v }: { visual: Visual }) {
    const [broken, setBroken] = useState(false);
    useEffect(() => setBroken(false), [v.logo_url]);
    const filled = v.show_launcher_bg;
    const radius = { circle: "50%", rounded: "12px", square: "0", oval: "40px" }[v.launcher_shape];
    const icon = Math.min(v.logo_size, 56);
    const label = v.launcher_label.trim();
    if (label) {
        return (
            <div className="flex items-center gap-2 h-[52px] pl-3.5 pr-5 rounded-full whitespace-nowrap text-[15px] font-semibold"
                 style={{ background: filled ? v.color : "transparent", color: filled ? v.text_color : v.color,
                          boxShadow: filled ? "0 4px 20px rgba(0,0,0,0.2)" : undefined, fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif" }}>
                {v.logo_url && !broken
                    ? <img src={assetUrl(v.logo_url)} alt="" onError={() => setBroken(true)} className="h-[26px] w-[26px] object-contain" />
                    : <svg viewBox="0 0 24 24" width={26} height={26} fill="currentColor" aria-hidden>
                        <path d="M12 2C6.477 2 2 6.477 2 12c0 1.821.487 3.53 1.338 5L2.5 21.5l4.5-.838A9.955 9.955 0 0012 22c5.523 0 10-4.477 10-10S17.523 2 12 2zm0 18c-1.476 0-2.886-.313-4.156-.872l-2.618.487.487-2.618A7.955 7.955 0 014 12c0-4.411 3.589-8 8-8s8 3.589 8 8-3.589 8-8 8z" />
                      </svg>}
                {label}
            </div>
        );
    }
    return (
        <div className="relative flex items-center justify-center"
             style={{
                 width: v.launcher_shape === "oval" ? 80 : 60, height: 60, borderRadius: radius,
                 background: filled ? v.color : "transparent",
                 boxShadow: filled ? "0 4px 20px rgba(0,0,0,0.2)" : undefined,
                 border: !filled && !v.logo_url ? "1px solid rgba(0,0,0,0.1)" : undefined,
             }}>
            {v.logo_url && !broken
                ? <img src={assetUrl(v.logo_url)} alt="" onError={() => setBroken(true)} className="object-contain max-w-[80%] max-h-[80%]" style={{ width: icon, height: icon }} />
                : <svg viewBox="0 0 24 24" width={28} height={28} fill={filled ? "#fff" : v.color} aria-hidden>
                    <path d="M12 2C6.477 2 2 6.477 2 12c0 1.821.487 3.53 1.338 5L2.5 21.5l4.5-.838A9.955 9.955 0 0012 22c5.523 0 10-4.477 10-10S17.523 2 12 2zm0 18c-1.476 0-2.886-.313-4.156-.872l-2.618.487.487-2.618A7.955 7.955 0 014 12c0-4.411 3.589-8 8-8s8 3.589 8 8-3.589 8-8 8z" />
                  </svg>}
            {v.show_tail && (
                <span className="absolute -bottom-1.5 -z-10" style={{
                    [v.position === "left" ? "left" : "right"]: v.launcher_shape === "oval" ? 20 : 10,
                    width: 0, height: 0, borderLeft: "10px solid transparent", borderRight: "10px solid transparent",
                    borderTop: `12px solid ${filled ? v.color : "transparent"}`,
                    transform: `rotate(${v.position === "left" ? 15 : -15}deg)`,
                }} />
            )}
        </div>
    );
}

/* ---------- The chat itself (as in app/widget/[botId]/page.tsx) ---------- */

function ChatWindow({ visual: v, botName, callbacks }: { visual: Visual; botName: string; callbacks: boolean }) {
    const [mode, setMode] = useState<"ai" | "human">("ai");
    const [broken, setBroken] = useState(false);
    useEffect(() => setBroken(false), [v.logo_url]);
    const radius = `${v.border_radius}px`;
    const footerLight = !!v.footer_bg_color && isLight(v.footer_bg_color);
    const name = botName || "Assistant";
    const welcome = v.welcome_message.trim() || `Hi! I'm ${name}. How can I help you today?`;
    const chip = "px-3 py-1.5 rounded-full text-xs border";

    const bubble = (from: "bot" | "user", children: ReactNode) => (
        <div className={`flex ${from === "user" ? "justify-end" : "justify-start"} items-start gap-2`}>
            {from === "bot" && (
                <div className="w-7 h-7 rounded-full flex items-center justify-center text-white shrink-0 mt-1"
                     style={{ backgroundColor: mode === "human" ? "#16a34a" : v.color }}>
                    <Bot size={14} />
                </div>
            )}
            <div className="px-4 py-3 text-[13px] leading-relaxed max-w-[85%] whitespace-pre-wrap shadow-sm"
                 style={{
                     borderRadius: radius,
                     backgroundColor: from === "user" ? v.user_bubble_bg : v.assistant_bubble_bg,
                     color: from === "user" ? v.user_bubble_text : v.assistant_bubble_text,
                     borderTopRightRadius: from === "user" ? 0 : undefined,
                     borderTopLeftRadius: from === "bot" ? 0 : undefined,
                 }}>
                {children}
            </div>
        </div>
    );

    return (
        <div className="flex flex-col h-full overflow-hidden relative" style={{ fontFamily: v.font_family, backgroundColor: v.chat_bg_color }}>
            {v.background_image && (
                <div className="absolute inset-0 pointer-events-none" style={{
                    backgroundImage: `url(${assetUrl(v.background_image)})`, backgroundSize: "cover", backgroundPosition: "center", opacity: v.background_opacity,
                }} />
            )}
            <header className="p-4 flex flex-col justify-center gap-3 shrink-0 shadow-lg relative z-20 border-b border-white/10"
                    style={{ backgroundColor: v.color, color: v.text_color, minHeight: v.header_height, borderTopLeftRadius: radius, borderTopRightRadius: radius }}>
                <div className="flex items-center gap-3 min-w-0">
                    <img src={v.logo_url && !broken ? assetUrl(v.logo_url) : "/favicon.png"} alt="" onError={() => setBroken(true)}
                         className="w-10 h-10 rounded-full border-2 border-white/50 object-cover shrink-0 bg-white" />
                    <div className="flex flex-col min-w-0 flex-1">
                        <span className="font-bold text-sm tracking-tight truncate">{name}</span>
                        <span className="text-[11px] opacity-75 font-medium truncate">{mode === "human" ? "Chatting with our team" : (v.subtitle || "Usually replies instantly")}</span>
                    </div>
                    <span className="p-2 -mr-1 opacity-70 shrink-0"><X size={18} /></span>
                </div>
                {v.show_human_toggle && (
                    <div role="radiogroup" aria-label="Chat with" className="grid grid-cols-2 bg-black/20 p-0.5 rounded-full border border-white/10">
                        {(["ai", "human"] as const).map((m) => (
                            <button key={m} type="button" role="radio" aria-checked={mode === m} onClick={() => setMode(m)}
                                    className={`py-1 rounded-full text-[11px] font-semibold transition-colors ${mode === m ? "bg-white text-black" : "opacity-75 hover:opacity-100"}`}>
                                {m === "ai" ? "Assistant" : "Talk to a person"}
                            </button>
                        ))}
                    </div>
                )}
            </header>

            <main className="flex-1 overflow-hidden p-5 space-y-3 relative z-10">
                {mode === "human" ? (
                    bubble("bot", "We've let our team know. Someone will join this chat shortly.")
                ) : (
                    <>
                        {bubble("bot", welcome)}
                        {v.starters.length > 0 && (
                            <div className="flex flex-wrap gap-2 pl-9">
                                {v.starters.map((q) => <span key={q} className={chip} style={{ borderColor: v.color, color: v.color }}>{q}</span>)}
                            </div>
                        )}
                        {bubble("user", "What are your opening hours?")}
                        {bubble("bot", "We're open Monday to Saturday, 9 AM to 7 PM. Would you like to book a visit?")}
                    </>
                )}
            </main>

            <footer className={`p-4 border-t flex flex-col gap-2 relative z-10 ${v.footer_bg_color ? (footerLight ? "border-black/5" : "border-white/5") : "bg-zinc-900/80 border-white/5 backdrop-blur-md"}`}
                    style={v.footer_bg_color ? { backgroundColor: v.footer_bg_color } : undefined}>
                {callbacks && mode === "ai" && (
                    <span className={`self-start text-[11px] underline underline-offset-2 px-1 ${footerLight ? "text-stone-600" : "text-white/70"}`}>
                        Prefer a call? Ask us to call you back
                    </span>
                )}
                <div className="flex gap-2 w-full">
                    <div className={`flex-1 rounded-xl border h-12 px-4 text-sm flex items-center ${footerLight ? "border-black/10" : "border-white/5"}`}
                         style={{ backgroundColor: v.input_bg_color, color: v.input_text_color }}>
                        <span className="opacity-50 truncate">{v.input_placeholder || "Type a message..."}</span>
                    </div>
                    <span className="w-12 h-12 shrink-0 rounded-xl flex items-center justify-center" style={{ backgroundColor: v.color, color: v.text_color }}>
                        <Send size={18} />
                    </span>
                </div>
                <p className={`text-center text-[10px] leading-none -mb-1 ${footerLight ? "text-stone-400" : "text-white/40"}`}>
                    Powered by <span className={`font-semibold ${footerLight ? "text-stone-500" : "text-white/60"}`}>Nimmi</span>
                </p>
            </footer>
        </div>
    );
}
