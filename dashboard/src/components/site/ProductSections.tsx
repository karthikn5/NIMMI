import Link from "next/link";
import type { CSSProperties } from "react";
import { ArrowRight, Check, Globe, MessageCircle, Phone } from "lucide-react";
import {
    CallSummaryPreview, CampaignPreview, ChatPreview, DataPreview, FunctionPreview, LiveChatPreview, MemoryPreview,
    SchedulePreview, TranscriptPreview, WhatsAppPreview,
} from "./Previews";
import { Container, Eyebrow, Heading, Lead, PrimaryLink, Section, SecondaryLink } from "./primitives";
import ProductTour from "./ProductTour";

export const LANGUAGES = ["English", "Hindi", "Tamil", "Telugu", "Kannada", "Malayalam", "Marathi", "Bengali", "Gujarati", "Punjabi", "Odia"];

export function Ticks({ items, dark }: { items: string[]; dark?: boolean }) {
    return (
        <ul className="space-y-2.5">
            {items.map((t) => (
                <li key={t} className={`flex gap-2.5 text-[15px] leading-snug ${dark ? "text-white/80" : "text-stone-700"}`}>
                    <Check size={16} className={`shrink-0 mt-0.5 ${dark ? "text-[#d9b8e0]" : "text-plum"}`} aria-hidden />{t}
                </li>
            ))}
        </ul>
    );
}

export function Hero() {
    return (
        <section className="relative isolate pt-28 sm:pt-36 pb-20 sm:pb-24">
            {/* Brand wash: soft plum at the top, fading into the page's paper colour. */}
            <div aria-hidden className="absolute inset-0 -z-10" style={{
                background: [
                    "radial-gradient(70% 60% at 12% 0%, #ecdcf0 0%, rgba(236,220,240,0) 70%)",
                    "radial-gradient(55% 50% at 92% 8%, #f1e8f4 0%, rgba(241,232,244,0) 70%)",
                    "linear-gradient(180deg, #f4ecf6 0%, #f8f4f8 55%, #faf9f7 100%)",
                ].join(", "),
            }} />
            <Container className="grid lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] gap-14 lg:gap-12 items-center">
                <div>
                    {/* One heading for search engines (what Nimmi is, then the promise), drawn as the two lines it always was. */}
                    <h1>
                        <span className="site-rise block text-[14px] text-stone-600 mb-5">AI voice agent and chatbot for website chat, WhatsApp and phone calls</span>
                        <span className="site-rise block font-display text-[42px] sm:text-[62px] leading-[1.02] font-medium tracking-[-0.03em] text-balance" style={{ "--rise-delay": "80ms" } as CSSProperties}>
                            Every customer answered, <span className="text-plum">in their language.</span>
                        </span>
                    </h1>
                    <p className="site-rise text-[18px] leading-relaxed text-stone-600 mt-6 max-w-xl" style={{ "--rise-delay": "180ms" } as CSSProperties}>
                        Nimmi is an assistant trained on your business. It answers questions, captures leads and books appointments
                        in English, Hindi, Tamil and eight more Indian languages, and hands the conversation to your team when it should.
                    </p>
                    <div className="site-rise flex flex-col sm:flex-row gap-3 mt-8" style={{ "--rise-delay": "260ms" } as CSSProperties}>
                        <PrimaryLink href="/auth/signup">Start free <ArrowRight size={16} /></PrimaryLink>
                        <SecondaryLink href="#how">See how it works</SecondaryLink>
                    </div>
                    <p className="site-rise text-[13px] text-stone-500 mt-5" style={{ "--rise-delay": "320ms" } as CSSProperties}>Start free with one assistant and one website. Plans from ₹833 a month, billed yearly.</p>
                </div>

                <div className="site-rise relative mx-auto w-full max-w-[460px] lg:max-w-none" style={{ "--rise-delay": "200ms" } as CSSProperties}>
                    <ChatPreview className="w-[88%]" />
                    <CallSummaryPreview className="w-[72%] ml-auto -mt-3 relative" />
                </div>
            </Container>
        </section>
    );
}

export function Channels() {
    const channels = [
        {
            icon: Globe, name: "Website chat", href: "/ai-chatbot-for-website", more: "Website chatbot",
            items: ["A chat window in your colours, live in one line of code", "Flows for forms and qualifying questions",
                    "Visitors can switch to a person at any time", "A call-back button for people who'd rather talk"],
        },
        {
            icon: MessageCircle, name: "WhatsApp", href: "/whatsapp-chatbot", more: "WhatsApp chatbot",
            items: ["Replies day and night on your WhatsApp Business number", "Understands Tanglish and Hinglish, and replies in kind",
                    "Your team takes over from Live chat when needed", "Confirms bookings made on calls"],
        },
        {
            icon: Phone, name: "Phone calls", href: "/ai-voice-agent", more: "AI voice agent",
            items: ["Answers calls on your business number", "Calls back new leads within a minute",
                    "Transfers to your team with a one-line brief", "Recording, transcript and summary for every call"],
        },
    ];
    return (
        <Section id="product" tone="white">
            <Container>
                <Eyebrow>One assistant</Eyebrow>
                <Heading>Everywhere your customers already reach you.</Heading>
                <Lead>Train it once. The same knowledge, tone and rules apply on your website, on WhatsApp and on the phone, and every conversation lands in one place.</Lead>
                <div className="grid md:grid-cols-3 gap-px bg-line border border-line rounded-lg overflow-hidden mt-12">
                    {channels.map(({ icon: Icon, name, items, href, more }, i) => (
                        <div key={name} data-reveal style={{ "--reveal-delay": `${i * 90}ms` } as CSSProperties} className="bg-white p-6 sm:p-7">
                            <Icon size={20} className="text-plum" aria-hidden />
                            <h3 className="font-display text-[19px] font-medium mt-4 mb-4">{name}</h3>
                            <Ticks items={items} />
                            <Link href={href} className="inline-flex items-center gap-1.5 mt-6 text-[14px] font-medium text-plum hover:underline underline-offset-4">
                                {more} <ArrowRight size={14} />
                            </Link>
                        </div>
                    ))}
                </div>
            </Container>
        </Section>
    );
}

export function Tour() {
    return (
        <Section id="tour">
            <Container>
                <Eyebrow>Inside the product</Eyebrow>
                <Heading>See what you get on day one.</Heading>
                <Lead>The screens your team will use every day: setting up an assistant, reading calls, following up on leads and answering what it couldn&apos;t.</Lead>
                <ProductTour />
            </Container>
        </Section>
    );
}

export function Voice() {
    const points = [
        { title: "Finds out what you need", text: "You choose the details to collect, like budget or preferred date. Each call is judged against your goal." },
        { title: "Every call on record", text: "Recording, transcript and a short summary for every call, with the caller's mood and a lead score." },
        { title: "Sounds like a real office", text: "Optional background sound, a pronunciation guide for brand names, and voicemail handling for outbound calls." },
        { title: "Built for India's rules", text: "Says it's automated and recorded, honours opt-out phrases, keeps a do-not-call list and deletes recordings on schedule." },
    ];
    return (
        <Section id="voice" tone="dark">
            <Container>
                <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)] gap-14 items-start">
                    <div>
                        <Eyebrow dark>Phone calls</Eyebrow>
                        <Heading>A receptionist that never misses a call.</Heading>
                        <Lead dark>Your assistant picks up on the first ring, answers from your own information, books what needs booking and writes it all down for you.</Lead>
                        <dl className="grid sm:grid-cols-2 gap-x-8 gap-y-7 mt-12">
                            {points.map((p, i) => (
                                <div key={p.title} data-reveal style={{ "--reveal-delay": `${(i % 2) * 80}ms` } as CSSProperties}>
                                    <dt className="text-[15px] font-semibold">{p.title}</dt>
                                    <dd className="text-[14px] leading-relaxed text-white/65 mt-1.5">{p.text}</dd>
                                </div>
                            ))}
                        </dl>
                        <Link href="/ai-voice-agent" className="inline-flex items-center gap-1.5 mt-10 text-[15px] font-medium text-[#d9b8e0] hover:underline underline-offset-4">
                            More about the AI voice agent <ArrowRight size={15} />
                        </Link>
                    </div>
                    <div className="lg:sticky lg:top-24 space-y-4">
                        <TranscriptPreview />
                        <p className="text-[13px] text-white/55">{LANGUAGES.join(" · ")}</p>
                    </div>
                </div>
            </Container>
        </Section>
    );
}

export function Outbound() {
    return (
        <Section id="campaigns">
            <Container className="grid lg:grid-cols-2 gap-14 items-center">
                <div className="order-2 lg:order-1"><CampaignPreview /></div>
                <div className="order-1 lg:order-2">
                    <Eyebrow>Call-backs and campaigns</Eyebrow>
                    <Heading>Call back every lead while they&apos;re still interested.</Heading>
                    <Lead>When someone leaves their number and asks for a call, your assistant rings them within a minute. For a whole list, run a campaign.</Lead>
                    <div className="mt-8"><Ticks items={[
                        "Upload a list and personalise each call with details like name, unit or date",
                        "Calling hours, retries and calls at once, set per campaign",
                        "Leaves a voicemail or tries again later when nobody answers",
                        "Live progress, with results you can export",
                        "Only people who agreed to be called, as TRAI requires",
                    ]} /></div>
                </div>
            </Container>
        </Section>
    );
}

export function Insights() {
    return (
        <Section id="data" tone="white">
            <Container className="grid lg:grid-cols-2 gap-14 items-center">
                <div>
                    <Eyebrow>Collected data</Eyebrow>
                    <Heading>Know what every conversation was worth.</Heading>
                    <Lead>Decide what your assistant should find out. After each chat or call you get those details in a table, with a lead score and whether the conversation reached its goal.</Lead>
                    <div className="mt-8"><Ticks items={[
                        "Your own fields: text, numbers, dates, yes or no, a list of choices",
                        "Hot, warm and cold leads, so your team calls the right people first",
                        "Questions it couldn't answer, grouped, so you can teach it in one place",
                        "Export to CSV, or send everything to your CRM as it happens",
                    ]} /></div>
                </div>
                <DataPreview />
            </Container>
        </Section>
    );
}

export function Team() {
    return (
        <Section id="team">
            <Container className="grid lg:grid-cols-2 gap-14 items-center">
                <div className="order-2 lg:order-1"><LiveChatPreview /></div>
                <div className="order-1 lg:order-2">
                    <Eyebrow>Live chat</Eyebrow>
                    <Heading>Your team steps in at the right moment.</Heading>
                    <Lead>When a customer asks for a person, or is clearly unhappy, the assistant brings in your team. They reply from one inbox for the website and WhatsApp.</Lead>
                    <div className="mt-8"><Ticks items={[
                        "Internal notes your customers never see",
                        "Saved replies for the questions your team answers every day",
                        "Business hours, holidays and an away message",
                        "Owner, admin and agent roles for your staff",
                    ]} /></div>
                    <Link href="/auth/signup" className="inline-flex items-center gap-1.5 mt-8 text-[15px] font-medium text-plum hover:underline underline-offset-4">
                        Try it with your team <ArrowRight size={15} />
                    </Link>
                </div>
            </Container>
        </Section>
    );
}

export function WhatsApp() {
    return (
        <Section id="whatsapp">
            <Container className="grid lg:grid-cols-2 gap-14 items-center">
                <div className="order-2 lg:order-1"><WhatsAppPreview /></div>
                <div className="order-1 lg:order-2">
                    <Eyebrow>WhatsApp</Eyebrow>
                    <Heading>On WhatsApp, it chats like a person.</Heading>
                    <Lead>It waits for customers to finish typing, shows that it&apos;s typing, and answers in short messages. It understands voice notes, photos and PDFs, and sends your brochure or price list when that helps.</Lead>
                    <div className="mt-8"><Ticks items={[
                        "Listens to voice notes in Tamil, Hindi, English and more",
                        "Reads the photos and PDFs customers send, like a form or a receipt",
                        "Sends your brochures, price lists and menus from your files",
                        "Quick-reply buttons for common choices",
                        "Your team can take over any chat from the inbox",
                    ]} /></div>
                    <Link href="/whatsapp-chatbot" className="inline-flex items-center gap-1.5 mt-8 text-[15px] font-medium text-plum hover:underline underline-offset-4">
                        More about the WhatsApp chatbot <ArrowRight size={15} />
                    </Link>
                </div>
            </Container>
        </Section>
    );
}

export function Memory() {
    return (
        <Section id="memory" tone="white">
            <Container className="grid lg:grid-cols-2 gap-14 items-center">
                <div>
                    <Eyebrow>Caller memory</Eyebrow>
                    <Heading>Greets returning callers by name.</Heading>
                    <Lead>When someone calls again, the assistant knows who they are and what they asked last time, from earlier calls and WhatsApp chats. It picks up where you left off, without asking the same questions twice.</Lead>
                    <div className="mt-8"><Ticks items={[
                        "Their name, the details they gave and what each call was about",
                        "Your team's notes, read before the next call",
                        "Separate agents for incoming and outgoing calls, each with its own opening and manner",
                        "Scripts written with AI: answer a few questions and get the opening, instructions and goal",
                        "Forgets a caller on request, and never reads out their number",
                    ]} /></div>
                </div>
                <MemoryPreview />
            </Container>
        </Section>
    );
}

export function FollowUps() {
    const points = [
        { title: "Call-backs when asked", text: "“Call me after 10 minutes” or “tomorrow at 11”: it books the time during the call and rings them then, from the number they called." },
        { title: "Follow-ups that know the lead", text: "After each call it rates the lead hot, warm or cold and writes what the next call should say. Your rules set how many, and how far apart." },
        { title: "Meetings you approve", text: "It offers your free times and books one. You approve, it calls to confirm, and the joining link reaches them on WhatsApp or email before it starts." },
        { title: "Within the rules", text: "Calling hours, opt-outs and India's 7‑day consent rule are built in. Turn on a review step to check each follow-up before it's made." },
    ];
    return (
        <Section id="schedule" tone="white">
            <Container>
                <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)] gap-14 items-start">
                    <div>
                        <Eyebrow>Follow-ups and meetings</Eyebrow>
                        <Heading>Every lead followed up. Every meeting confirmed.</Heading>
                        <Lead>Your assistant keeps working after the call ends. It calls back when people ask, follows up with leads by how interested they sounded, and books meetings with your team.</Lead>
                        <dl className="grid sm:grid-cols-2 gap-x-8 gap-y-7 mt-12">
                            {points.map((p, i) => (
                                <div key={p.title} data-reveal style={{ "--reveal-delay": `${(i % 2) * 80}ms` } as CSSProperties}>
                                    <dt className="text-[15px] font-semibold">{p.title}</dt>
                                    <dd className="text-[14px] leading-relaxed text-stone-600 mt-1.5">{p.text}</dd>
                                </div>
                            ))}
                        </dl>
                        <Link href="/lead-management" className="inline-flex items-center gap-1.5 mt-10 text-[15px] font-medium text-plum hover:underline underline-offset-4">
                            How AI lead management works <ArrowRight size={15} />
                        </Link>
                    </div>
                    <div className="lg:sticky lg:top-24">
                        <SchedulePreview />
                    </div>
                </div>
            </Container>
        </Section>
    );
}

export function Connected() {
    return (
        <Section id="functions">
            <Container className="grid lg:grid-cols-2 gap-14 items-center">
                <div className="order-2 lg:order-1"><FunctionPreview /></div>
                <div className="order-1 lg:order-2">
                    <Eyebrow>Connected to your systems</Eyebrow>
                    <Heading>Looks it up while they&apos;re on the line.</Heading>
                    <Lead>Connect your own systems and calendar. During the call the assistant checks an order, a booking or a free slot, and answers from what it finds.</Lead>
                    <div className="mt-8"><Ticks items={[
                        "Your own API: order status, balances, delivery dates and more",
                        "Cal.com: checks free slots and books appointments on the call",
                        "Asks for the details it needs first, and never makes up an answer",
                        "Keys and passwords are stored encrypted, never shown in full",
                        "Choose each agent's AI model, from low-cost to the smartest",
                    ]} /></div>
                </div>
            </Container>
        </Section>
    );
}
