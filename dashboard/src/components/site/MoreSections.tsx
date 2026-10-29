import Image from "next/image";
import Link from "next/link";
import type { CSSProperties } from "react";
import { ArrowRight, ArrowUpRight, Instagram, Mail, Plus } from "lucide-react";
import CallRates from "./CallRates";
import PricingTable from "./PricingTable";
import { Container, Eyebrow, Heading, Lead, PrimaryLink, Section, SecondaryLink } from "./primitives";

export function HowItWorks() {
    const steps = [
        { title: "Teach it your business", text: "Add your website pages, PDFs, YouTube videos or a few FAQs. Or start from a template for your industry and fill in the blanks." },
        { title: "Choose where it works", text: "Paste one line of code on your website, connect your WhatsApp Business number, and get a phone number for calls." },
        { title: "Watch it and improve it", text: "Read every chat, listen to every call, and answer the questions it couldn't. It uses your answers from then on." },
    ];
    return (
        <Section id="how" tone="white">
            <Container>
                <Eyebrow>How it works</Eyebrow>
                <Heading>Live this afternoon, better every week.</Heading>
                <ol className="grid md:grid-cols-3 gap-10 md:gap-8 mt-12">
                    {steps.map((s, i) => (
                        <li key={s.title} data-reveal style={{ "--reveal-delay": `${i * 100}ms` } as CSSProperties} className="border-t border-line-strong pt-5">
                            <span className="text-[13px] font-medium text-plum tabular-nums">Step {i + 1}</span>
                            <h3 className="font-display text-[20px] font-medium mt-2">{s.title}</h3>
                            <p className="text-[15px] leading-relaxed text-stone-600 mt-2">{s.text}</p>
                        </li>
                    ))}
                </ol>
            </Container>
        </Section>
    );
}

export function Integrations() {
    const items = [
        { name: "Email", text: "Lead alerts to your team, and automatic follow-ups to customers with your name and reply address." },
        { name: "WhatsApp Business", text: "Two-way AI chat on your own number, plus confirmations after calls." },
        { name: "Webhooks", text: "Every lead and call, signed, to your own system, Zapier, Make or Zoho Flow." },
        { name: "LeadSquared", text: "Leads created or updated automatically, matched on phone and email." },
        { name: "Google Sheets", text: "Add a row for each lead straight from a chat flow." },
        { name: "Phone numbers", text: "Indian numbers through Exotel, or local numbers in the US, UK, Canada and Australia." },
    ];
    return (
        <Section id="integrations">
            <Container>
                <Eyebrow>Integrations</Eyebrow>
                <Heading>Fits the way you already work.</Heading>
                <Lead>Leads and summaries go where your team looks: their inbox, your CRM or a spreadsheet.</Lead>
                <ul className="grid sm:grid-cols-2 lg:grid-cols-3 gap-px bg-line border border-line rounded-lg overflow-hidden mt-12">
                    {items.map((it, i) => (
                        <li key={it.name} data-reveal style={{ "--reveal-delay": `${(i % 3) * 80}ms` } as CSSProperties} className="bg-white p-6">
                            <h3 className="text-[15px] font-semibold">{it.name}</h3>
                            <p className="text-[14px] leading-relaxed text-stone-600 mt-1.5">{it.text}</p>
                        </li>
                    ))}
                </ul>
            </Container>
        </Section>
    );
}

export function Industries() {
    const list = [
        { name: "Real estate", text: "Project questions, site visits and loan enquiries.", href: "/solutions/real-estate" },
        { name: "Coaching and colleges", text: "Admissions, fees and counselling sessions." },
        { name: "Clinics and hospitals", text: "Doctor timings and appointments, never medical advice.", href: "/solutions/healthcare" },
        { name: "Online stores", text: "Order questions, returns and cash-on-delivery checks.", href: "/solutions/ecommerce" },
        { name: "Restaurants", text: "Menus, timings and table bookings." },
        { name: "Salons and spas", text: "Services, prices and appointments." },
        { name: "Travel", text: "Packages, visas and trip enquiries." },
        { name: "Insurance and loans", text: "Plan questions and qualified leads for advisors." },
    ];
    return (
        <Section id="industries" tone="white">
            <Container>
                <Eyebrow>Industries</Eyebrow>
                <Heading>Start from a template made for your business.</Heading>
                <Lead>Each one sets up the assistant&apos;s instructions, a knowledge sheet to fill in, and what to ask callers. Change anything later.</Lead>
                <ul className="grid sm:grid-cols-2 lg:grid-cols-4 gap-x-8 gap-y-8 mt-12">
                    {list.map((it, i) => (
                        <li key={it.name} data-reveal style={{ "--reveal-delay": `${(i % 4) * 70}ms` } as CSSProperties} className="border-t border-line pt-4">
                            {it.href ? (
                                <Link href={it.href} className="group inline-flex items-center gap-1 text-[15px] font-semibold hover:text-plum">
                                    {it.name} <ArrowUpRight size={14} className="text-stone-400 group-hover:text-plum" />
                                </Link>
                            ) : <h3 className="text-[15px] font-semibold">{it.name}</h3>}
                            <p className="text-[14px] leading-relaxed text-stone-600 mt-1.5">{it.text}</p>
                        </li>
                    ))}
                </ul>
            </Container>
        </Section>
    );
}

const PACKS = [["100 credits", "₹549", "₹5.49"], ["500 credits", "₹2,499", "₹5.00"], ["1,000 credits", "₹4,499", "₹4.50"]];

export function Pricing() {
    return (
        <Section id="pricing">
            <Container>
                <Eyebrow>Pricing</Eyebrow>
                <Heading>Simple plans that grow with you.</Heading>
                <Lead>Start free with one assistant, one published website and 10 call credits. Phone calls are pay as you go; integrations and custom domains come with a paid plan. Prices are per assistant.</Lead>

                <PricingTable />

                <div className="grid md:grid-cols-3 gap-px bg-line border border-line rounded-lg overflow-hidden mt-6">
                    <div className="bg-white p-6">
                        <h3 className="text-[15px] font-semibold">Call credits</h3>
                        <p className="text-[13px] text-stone-500 mt-1">
                            Pay as you go, on any plan. A call minute is 1 credit plus the AI model&apos;s rate below. Credits don&apos;t expire.
                        </p>
                        <ul className="mt-3 divide-y divide-line">
                            {PACKS.map(([m, p, per]) => (
                                <li key={m} className="flex justify-between gap-3 py-2 text-[14px]">
                                    <span>{m}</span>
                                    <span className="tabular-nums"><span className="font-medium">{p}</span> <span className="text-stone-500 text-[12px]">({per} each)</span></span>
                                </li>
                            ))}
                        </ul>
                    </div>
                    <div className="bg-white p-6">
                        <h3 className="text-[15px] font-semibold">Phone numbers</h3>
                        <p className="text-[14px] leading-relaxed text-stone-600 mt-1.5">
                            Indian numbers through Exotel need your business documents, as telecom rules require.
                            Numbers in the US, UK, Canada and Australia are instant, from ₹99 a month.
                        </p>
                    </div>
                    <div className="bg-white p-6 flex flex-col">
                        <h3 className="text-[15px] font-semibold">Agencies and larger teams</h3>
                        <p className="text-[14px] leading-relaxed text-stone-600 mt-1.5">
                            Many assistants, higher limits, custom voices or volume call pricing. We&apos;ll put a plan together with you.
                        </p>
                        <a href="mailto:support.nimmi@gmail.com" className="inline-flex items-center gap-1.5 mt-auto pt-4 text-[14px] font-medium text-plum hover:underline underline-offset-4">
                            Talk to us <ArrowRight size={14} />
                        </a>
                    </div>
                </div>

                <div id="rates" className="mt-10 scroll-mt-24">
                    <h3 className="font-display text-[19px] font-medium">Call rates by AI model</h3>
                    <p className="text-[14px] text-stone-600 mt-1 max-w-[62ch]">
                        Choose the AI model for each agent. Quicker models cost less; the smarter ones handle detailed questions.
                    </p>
                    <CallRates />
                </div>
            </Container>
        </Section>
    );
}

export const FAQS = [
    { q: "Which languages does it speak?", a: "English, Hindi, Tamil, Telugu, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi and Odia. On calls it also follows callers who mix English into their language, like Tanglish or Hinglish." },
    { q: "How do I train it on my business?", a: "Add your website pages, PDFs, YouTube videos or plain text, or start from an industry template. When it can't answer something, the question appears on your Questions page; answer it once and it uses that answer from then on." },
    { q: "Can it answer calls on my existing number?", a: "Yes. You can forward your number to a Nimmi number, or get a new one. Indian numbers come through Exotel and need your Certificate of Incorporation and GST certificate; numbers in other countries are available instantly." },
    { q: "What happens when a customer wants a real person?", a: "On chat and WhatsApp, the conversation moves to your team's Live chat. On calls, it transfers to your number, with a short brief you hear first. Outside business hours, it takes a message instead." },
    { q: "Is it allowed to call my leads automatically?", a: "Only people who asked to be called or agreed to it. The assistant says it's automated and that the call may be recorded, honours requests to stop, and keeps a do-not-call list, in line with TRAI rules." },
    { q: "Can I try it before paying?", a: "Yes. The free plan includes one assistant to build and test, one website published on a free address, and 10 call credits to try phone calls. After that, calls are pay as you go with credit packs. Integrations and custom domains come with a paid plan, and you pay when you put an assistant live." },
    { q: "What counts as an AI reply?", a: "Each answer your assistant writes in website chat or WhatsApp. Replies your team sends from Live chat don't count. If you reach your plan's limit, we'll let you know before anything stops, and you can move up a plan." },
    { q: "Can it call people back at a time they choose?", a: "Yes. When a caller says “call me after 10 minutes” or “tomorrow at 11”, the assistant books it during the call and rings them then, from the number they called. A time outside your calling hours is moved to the nearest one, and the caller is told." },
    { q: "Does it follow up with leads by itself?", a: "When you turn it on. After each call it rates the lead hot, warm or cold and plans the next call by your rules, with what to say. You can check each follow-up before it's made. Follow-ups stop when someone books, says no or opts out, and seven days after they last spoke with you." },
    { q: "Can customers book a meeting with my team?", a: "Yes. The assistant offers your free times and books the one they pick. You approve it, the assistant calls to confirm, and they get a reminder and the joining link on WhatsApp or email before it starts." },
    { q: "Does it remember people who call again?", a: "Yes. It greets returning callers by name and remembers what earlier calls and WhatsApp chats were about, along with your team's notes. You can switch this off, or make it forget a caller." },
];

export function FAQ() {
    return (
        <Section id="faq" tone="white">
            <Container className="grid lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] gap-12">
                <div>
                    <Eyebrow>Questions</Eyebrow>
                    <Heading>Before you start.</Heading>
                    <p className="text-[15px] text-stone-600 mt-4">
                        Something else? Write to <a href="mailto:support.nimmi@gmail.com" className="text-plum hover:underline underline-offset-4">support.nimmi@gmail.com</a>.
                    </p>
                </div>
                <div className="border-t border-line">
                    {FAQS.map((f) => (
                        <details key={f.q} className="group border-b border-line">
                            <summary className="flex items-center justify-between gap-4 py-5 cursor-pointer list-none text-[16px] font-medium [&::-webkit-details-marker]:hidden">
                                {f.q}
                                <Plus size={18} className="shrink-0 text-stone-400 transition-transform group-open:rotate-45" aria-hidden />
                            </summary>
                            <p className="pb-5 -mt-1 text-[15px] leading-relaxed text-stone-600 max-w-2xl">{f.a}</p>
                        </details>
                    ))}
                </div>
            </Container>
        </Section>
    );
}

export function FinalCTA() {
    return (
        <Section tone="dark" className="py-20 sm:py-24">
            <Container className="flex flex-col lg:flex-row lg:items-end justify-between gap-8">
                <div>
                    <h2 data-reveal className="font-display text-[32px] sm:text-[48px] leading-[1.04] font-medium tracking-[-0.02em] max-w-xl text-balance">Set up your assistant today. Answer every customer tomorrow.</h2>
                    <p className="text-[17px] text-white/70 mt-4">Free to build and test. No card needed.</p>
                </div>
                <div className="flex flex-col sm:flex-row gap-3 shrink-0">
                    <PrimaryLink href="/auth/signup" className="bg-white text-aubergine hover:bg-stone-100">Start free <ArrowRight size={16} /></PrimaryLink>
                    <SecondaryLink href="mailto:support.nimmi@gmail.com" dark>Talk to us</SecondaryLink>
                </div>
            </Container>
        </Section>
    );
}

export function SiteFooter() {
    const cols = [
        { title: "Product", links: [["AI voice agent", "/ai-voice-agent"], ["WhatsApp chatbot", "/whatsapp-chatbot"], ["Website chatbot", "/ai-chatbot-for-website"],
                                    ["Lead management", "/lead-management"], ["Campaigns", "/#campaigns"], ["Live chat", "/#team"], ["Pricing", "/pricing"]] },
        { title: "Industries", links: [["Real estate", "/solutions/real-estate"], ["Healthcare", "/solutions/healthcare"], ["Online stores", "/solutions/ecommerce"]] },
        { title: "Resources", links: [["Blog", "/blog"], ["Build a custom AI chatbot", "/blog/how-to-build-custom-ai-chatbot-2026"], ["Chatbot ROI", "/blog/calculating-chatbot-roi"]] },
    ];
    return (
        <footer className="bg-paper border-t border-line">
            <Container className="py-14 grid gap-10 md:grid-cols-[minmax(0,1.4fr)_repeat(3,minmax(0,1fr))]">
                <div>
                    <Link href="/" className="inline-flex items-center gap-2">
                        <Image src="/favicon.png" alt="" width={26} height={26} />
                        <span className="text-[15px] font-semibold text-plum tracking-tight">Nimmi AI</span>
                    </Link>
                    <p className="text-[14px] text-stone-600 mt-3 max-w-xs leading-relaxed">AI assistants for website chat, WhatsApp and phone calls, built in India for Indian businesses.</p>
                    <div className="flex items-center gap-4 mt-5 text-[14px]">
                        <a href="mailto:support.nimmi@gmail.com" className="inline-flex items-center gap-1.5 text-stone-700 hover:text-plum"><Mail size={15} aria-hidden /> support.nimmi@gmail.com</a>
                        <a href="https://www.instagram.com/nimmiai.in" target="_blank" rel="noopener noreferrer" aria-label="Nimmi AI on Instagram" className="text-stone-500 hover:text-plum"><Instagram size={16} /></a>
                    </div>
                </div>
                {cols.map((c) => (
                    <div key={c.title}>
                        <h3 className="text-[13px] font-medium text-stone-500">{c.title}</h3>
                        <ul className="mt-3 space-y-2.5">
                            {c.links.map(([label, href]) => (
                                <li key={label}><Link href={href} className="text-[14px] text-stone-700 hover:text-plum">{label}</Link></li>
                            ))}
                        </ul>
                    </div>
                ))}
            </Container>
            <Container>
                <div className="py-6 border-t border-line flex flex-col sm:flex-row justify-between gap-2 text-[13px] text-stone-500">
                    <p>© {new Date().getFullYear()} Nimmi AI. Made in India.</p>
                    <a href="mailto:support.nimmi@gmail.com" className="hover:text-plum">Contact</a>
                </div>
            </Container>
        </footer>
    );
}
