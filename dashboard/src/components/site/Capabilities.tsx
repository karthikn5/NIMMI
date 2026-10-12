import Image from "next/image";
import type { CSSProperties, ReactNode } from "react";
import { Globe, Mail, MessageCircle, Phone, User } from "lucide-react";
import { Container, Eyebrow, Heading, Section } from "./primitives";

/* Four capability cards, each with a small live illustration (CSS-only motion; still under reduced motion). */

function Card({ title, text, children, delay = 0 }: { title: string; text: string; children: ReactNode; delay?: number }) {
    return (
        <div data-reveal style={{ "--reveal-delay": `${delay}ms` } as CSSProperties}
             className="relative flex flex-col rounded-2xl border border-line bg-white p-7 sm:p-8 overflow-hidden">
            <h3 className="font-display text-[22px] sm:text-[24px] font-medium tracking-tight">{title}</h3>
            <p className="text-[15px] leading-relaxed text-stone-500 mt-2 max-w-md">{text}</p>
            <div className="mt-8 flex-1 flex items-center justify-center min-h-[120px] sm:min-h-[190px]">{children}</div>
        </div>
    );
}

const GREETINGS = [
    ["Hello", "English"], ["नमस्ते", "Hindi"], ["வணக்கம்", "Tamil"], ["నమస్కారం", "Telugu"], ["ನಮಸ್ಕಾರ", "Kannada"],
    ["നമസ്കാരം", "Malayalam"], ["नमस्कार", "Marathi"], ["নমস্কার", "Bengali"], ["નમસ્તે", "Gujarati"], ["ਸਤ ਸ੍ਰੀ ਅਕਾਲ", "Punjabi"], ["ନମସ୍କାର", "Odia"],
];

function Languages() {
    return (
        <p className="site-glow flex flex-wrap justify-center gap-x-5 gap-y-3 max-w-[22rem] text-center text-[21px] sm:text-[23px] leading-tight">
            {GREETINGS.map(([word, lang], i) => (
                <span key={lang} lang={lang === "English" ? "en" : undefined} title={lang} style={{ animationDelay: `${i * 1.2}s` }}>{word}</span>
            ))}
        </p>
    );
}

const CALLER = [6, 14, 9, 20, 12, 26, 10, 18, 7, 15, 22, 9, 13, 6];
const AGENT = [10, 18, 26, 14, 22, 30, 16, 24, 12, 20];

function Latency() {
    return (
        <div className="w-full flex items-center gap-3">
            <div className="site-wave hidden sm:flex items-center gap-[3px] h-12 shrink-0" aria-hidden>
                {CALLER.map((h, i) => (
                    <span key={i} className="w-[3px] rounded-full bg-stone-300" style={{ height: h * 1.4, animationDelay: `${(i % 7) * 0.13}s` }} />
                ))}
            </div>
            <div className="flex-1 min-w-0 flex items-center gap-3 h-14 pl-3 pr-4 rounded-full bg-aubergine text-white">
                <div className="site-wave flex items-center gap-[3px] h-9 shrink-0" aria-hidden>
                    {AGENT.map((h, i) => (
                        <span key={i} className="w-[3px] rounded-full bg-[#d9b8e0]" style={{ height: h, animationDelay: `${(i % 5) * 0.17}s` }} />
                    ))}
                </div>
                <span className="text-[13px] truncate">Booked for Saturday, 11 AM</span>
            </div>
            <span className="sr-only">The assistant answers in about a second.</span>
        </div>
    );
}

function Handover() {
    return (
        <div className="w-full max-w-sm">
            <div className="flex items-center gap-3">
                <span className="shrink-0 inline-flex items-center gap-2 h-9 px-3 rounded-full border border-line bg-paper text-[13px]">
                    <Image src="/favicon.png" alt="" width={18} height={18} /> Assistant
                </span>
                <div className="relative flex-1 h-px bg-line-strong" aria-hidden>
                    <span className="site-travel absolute -top-[3px] h-[7px] w-[7px] -ml-[3px] rounded-full bg-plum" />
                </div>
                <span className="shrink-0 inline-flex items-center gap-2 h-9 px-3 rounded-full bg-ink text-white text-[13px]">
                    <User size={14} /> Your team
                </span>
            </div>
            <div className="mt-5 rounded-lg border border-line bg-paper px-4 py-3 text-[13px] leading-snug">
                <span className="block text-[11px] text-stone-500 mb-1">They hear first</span>
                Ravi wants a 2BHK under 65 lakhs and has booked a site visit for Saturday.
            </div>
        </div>
    );
}

const CHANNELS = [
    { y: 26, icon: Phone, label: "Phone" },
    { y: 70, icon: MessageCircle, label: "WhatsApp" },
    { y: 114, icon: Globe, label: "Website" },
    { y: 158, icon: Mail, label: "Email" },
];

function OneAssistant() {
    const W = 400, H = 184, cx = 205, cy = 92;
    const pct = (x: number, y: number): CSSProperties => ({ left: `${(x / W) * 100}%`, top: `${(y / H) * 100}%` });
    const curve = (y: number) => `M${cx + 22} ${cy} C ${cx + 80} ${cy}, ${cx + 90} ${y}, 344 ${y}`;
    return (
        <div className="relative w-full max-w-md" style={{ aspectRatio: `${W} / ${H}` }}>
            <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 w-full h-full" fill="none" aria-hidden>
                <path d={`M64 ${cy} H${cx - 22}`} stroke="#e8e5e0" strokeWidth="1.5" />
                {CHANNELS.map((c) => <path key={c.label} d={curve(c.y)} stroke="#e8e5e0" strokeWidth="1.5" />)}
                <path d={`M64 ${cy} H${cx - 22}`} stroke="#550a64" strokeWidth="1.5" strokeLinecap="round" className="site-dash" />
                {CHANNELS.map((c, i) => (
                    <path key={c.label} d={curve(c.y)} stroke="#550a64" strokeWidth="1.5" strokeLinecap="round" className="site-dash"
                          style={{ animationDelay: `${0.9 + i * 0.35}s` }} />
                ))}
            </svg>
            <span className="absolute -translate-x-1/2 -translate-y-1/2 h-10 w-10 rounded-full border border-line bg-white inline-flex items-center justify-center text-stone-500" style={pct(44, cy)}>
                <User size={17} />
            </span>
            <span className="absolute -translate-x-1/2 -translate-y-1/2 h-12 w-12 rounded-xl bg-aubergine inline-flex items-center justify-center shadow-[0_8px_24px_-8px_rgba(46,0,55,0.6)]" style={pct(cx, cy)}>
                <Image src="/favicon.png" alt="" width={26} height={26} />
            </span>
            {CHANNELS.map(({ y, icon: Icon, label }) => (
                <span key={label} title={label} className="absolute -translate-x-1/2 -translate-y-1/2 h-9 w-9 rounded-full border border-line bg-white inline-flex items-center justify-center text-stone-600" style={pct(362, y)}>
                    <Icon size={15} /><span className="sr-only">{label}</span>
                </span>
            ))}
        </div>
    );
}

export default function Capabilities() {
    return (
        <Section id="capabilities" tone="white">
            <Container>
                <div className="text-center flex flex-col items-center">
                    <Eyebrow>Why Nimmi</Eyebrow>
                    <Heading className="mx-auto text-center">Built for the way India talks to businesses.</Heading>
                </div>
                <div className="grid md:grid-cols-2 gap-5 mt-14">
                    <Card title="Speaks 11 Indian languages" text="And keeps up when callers switch to English mid-sentence, the way people really talk. Natural Indian voices for each.">
                        <Languages />
                    </Card>
                    <Card title="Replies in about a second" text="Callers can interrupt, change their mind or pause. It responds like someone on the line would." delay={90}>
                        <Latency />
                    </Card>
                    <Card title="Hands over with a brief" text="When a customer wants a person, your team hears a one-line summary before they're connected." delay={60}>
                        <Handover />
                    </Card>
                    <Card title="One assistant, every channel" text="Train it once. The same knowledge and rules answer on your website, WhatsApp and the phone, and your team hears about every lead by email." delay={150}>
                        <OneAssistant />
                    </Card>
                </div>
            </Container>
        </Section>
    );
}
