import type { Metadata } from "next";
import type { CSSProperties } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import JsonLd from "@/components/site/JsonLd";
import { FinalCTA } from "@/components/site/MoreSections";
import { PageFaq, PageHero, RelatedPages, SitePage } from "@/components/site/PageParts";
import { CallSummaryPreview, SchedulePreview, TranscriptPreview } from "@/components/site/Previews";
import { Container, Eyebrow, Heading, Lead, Section } from "@/components/site/primitives";
import { LANGUAGES, Ticks } from "@/components/site/ProductSections";
import { pageMetadata, productLd, type Faq } from "@/lib/site/seo";

const PATH = "/ai-voice-agent";
const DESCRIPTION = "AI voice agent that answers your business calls, calls back leads and books appointments in Tamil, Hindi, English and 8 more Indian languages. Start free.";

export const metadata: Metadata = pageMetadata({
    title: "AI Voice Agent in 11 Indian Languages",
    description: DESCRIPTION,
    path: PATH,
    image: "/og/voice.png",
    keywords: ["AI voice agent", "AI calling agent", "AI voice bot India", "AI receptionist", "AI telecaller", "voice AI for business",
               "Tamil voice bot", "Hindi AI calling", "AI phone answering", "AI call centre software"],
});

const JOBS = [
    { title: "Answers every incoming call", text: "An AI receptionist on your business number, day and night. It picks up on the first ring and answers from your own information." },
    { title: "Calls back new leads in a minute", text: "When someone fills a form or asks for a call in your website chat, an AI telecaller rings them while they're still interested." },
    { title: "Books appointments and meetings", text: "It checks your free times and books site visits, consultations or demos, then confirms with a call and a reminder." },
    { title: "Follows up until they decide", text: "After every call it rates the lead hot, warm or cold and plans the next call by your rules, with what to say." },
    { title: "Hands over with a brief", text: "When a caller wants a person, it transfers the call. Your team hears a one-line summary before they're connected." },
    { title: "Writes every call down", text: "Recording, transcript, summary, the details collected, the caller's mood and a lead score, for every call." },
];

const USES = [
    ["Missed and after-hours calls", "No more “call us back during office hours”. Every caller gets an answer and a next step."],
    ["Lead qualification", "Asks your questions, like budget, location or preferred date, and sends hot leads to your team first."],
    ["Appointment booking", "Clinics, salons, coaching centres and showrooms: the agent books the slot and confirms it."],
    ["Order and booking status", "Connected to your own system, it looks up an order or booking during the call and answers."],
    ["Campaign calls", "Calls a list of people who agreed to hear from you: reminders, renewals, event invites or feedback."],
    ["Call-backs on request", "“Call me after 10 minutes”: it books the time on the call and rings them then."],
];

const FAQS: Faq[] = [
    { q: "What is an AI voice agent?", a: "An AI voice agent is software that talks on the phone like a person. It listens, understands what the caller wants, and answers in a natural voice. Nimmi's voice agent answers your business calls, calls back leads, books appointments and passes calls to your team when needed." },
    { q: "Can it answer calls on my existing business number?", a: "Yes. Forward your existing number to a Nimmi number, or get a new one. Indian numbers come through Exotel and need your business documents, as telecom rules require. Numbers in the US, UK, Canada and Australia are available instantly." },
    { q: "Which languages does the AI voice agent speak?", a: "English, Hindi, Tamil, Telugu, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi and Odia. It follows callers who switch language mid-call, and understands mixed speech like Tanglish and Hinglish." },
    { q: "How fast does it reply on a call?", a: "In about a second, like a person on the line. Callers can interrupt it, change their mind or pause, and it keeps up." },
    { q: "Can it transfer a call to my team?", a: "Yes. When a caller asks for a person, it transfers the call to your number, and your team hears a short brief first. Outside business hours it takes a message instead, and your team gets it as a to-do." },
    { q: "Is AI calling legal in India?", a: "Yes, when you follow TRAI's rules. The agent says it's automated and that the call may be recorded, only calls people who asked or agreed to be called, honours opt-out requests and keeps a do-not-call list. By default, follow-ups stop seven days after someone last spoke with you." },
    { q: "How much does an AI voice agent cost?", a: "Calls are pay as you go with credits. A call minute is 1 credit plus the AI model's rate, counted in half-minutes. Credit packs start at ₹549 for 100 credits, and the free plan includes 10 credits to try it." },
];

export default function VoiceAgentPage() {
    return (
        <SitePage>
            <JsonLd data={productLd({ name: "Nimmi AI Voice Agent", description: DESCRIPTION, path: PATH })} />
            <PageHero
                crumb="AI voice agent" path={PATH}
                title={<>An AI voice agent that answers every call, <span className="text-plum">in 11 Indian languages.</span></>}
                lead="Nimmi picks up on the first ring, answers from your business information, books appointments and transfers to your team when it should. It also calls back new leads within a minute and follows up until they decide."
                secondary={{ href: "/pricing#rates", label: "See call rates" }}
                note="10 free call credits to try it. No card needed."
                preview={<><TranscriptPreview /><CallSummaryPreview className="w-[78%] ml-auto -mt-3 relative" /></>}
            />

            <Section tone="white">
                <Container>
                    <Eyebrow>What it does</Eyebrow>
                    <Heading>An AI receptionist and telecaller in one.</Heading>
                    <Lead>One agent for the calls you receive and another for the calls you make, each with its own opening, manner and script.</Lead>
                    <dl className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-8 mt-12">
                        {JOBS.map((j, i) => (
                            <div key={j.title} data-reveal style={{ "--reveal-delay": `${(i % 3) * 80}ms` } as CSSProperties} className="border-t border-line pt-4">
                                <dt className="text-[15px] font-semibold">{j.title}</dt>
                                <dd className="text-[14px] leading-relaxed text-stone-600 mt-1.5">{j.text}</dd>
                            </div>
                        ))}
                    </dl>
                </Container>
            </Section>

            <Section tone="dark">
                <Container className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)] gap-14 items-center">
                    <div>
                        <Eyebrow dark>Indian languages</Eyebrow>
                        <Heading>Speaks the way your callers speak.</Heading>
                        <Lead dark>Tamil, Hindi, Telugu, Kannada, Malayalam and six more languages, with natural Indian voices. When a caller switches from English to Tamil mid-call, the agent switches too.</Lead>
                        <div className="mt-8"><Ticks dark items={[
                            "Understands Tanglish, Hinglish and other mixed speech",
                            "Follows the caller's language, or stays in yours",
                            "A pronunciation guide for your brand and product names",
                            "Hears the caller over a TV or a busy room",
                        ]} /></div>
                    </div>
                    <ul className="grid grid-cols-2 sm:grid-cols-3 gap-px bg-white/10 border border-white/10 rounded-lg overflow-hidden">
                        {LANGUAGES.map((l) => <li key={l} className="bg-aubergine px-4 py-3 text-[14px] text-white/85">{l}</li>)}
                        <li className="bg-aubergine px-4 py-3 text-[14px] text-white/55">Mixed: Tanglish, Hinglish</li>
                    </ul>
                </Container>
            </Section>

            <Section>
                <Container>
                    <Eyebrow>Use cases</Eyebrow>
                    <Heading>Built for the calls your business gets every day.</Heading>
                    <ul className="grid sm:grid-cols-2 lg:grid-cols-3 gap-px bg-line border border-line rounded-lg overflow-hidden mt-12">
                        {USES.map(([title, text], i) => (
                            <li key={title} data-reveal style={{ "--reveal-delay": `${(i % 3) * 80}ms` } as CSSProperties} className="bg-white p-6">
                                <h3 className="text-[15px] font-semibold">{title}</h3>
                                <p className="text-[14px] leading-relaxed text-stone-600 mt-1.5">{text}</p>
                            </li>
                        ))}
                    </ul>
                </Container>
            </Section>

            <Section tone="white">
                <Container className="grid lg:grid-cols-2 gap-14 items-center">
                    <div>
                        <Eyebrow>After the call</Eyebrow>
                        <Heading>It keeps working when the call ends.</Heading>
                        <Lead>Call-backs people ask for, follow-ups by how interested they sounded, and meetings with your team that you approve, all in one list.</Lead>
                        <div className="mt-8"><Ticks items={[
                            "Remembers returning callers and greets them by name",
                            "Rates every lead hot, warm or cold, with the reason",
                            "Confirms meetings with a call and sends the link before they start",
                            "Sends every lead to your inbox, CRM or a spreadsheet",
                        ]} /></div>
                        <Link href="/lead-management" className="inline-flex items-center gap-1.5 mt-8 text-[15px] font-medium text-plum hover:underline underline-offset-4">
                            How AI lead management works <ArrowRight size={15} />
                        </Link>
                    </div>
                    <SchedulePreview />
                </Container>
            </Section>

            <Section>
                <Container className="grid lg:grid-cols-2 gap-14 items-start">
                    <div>
                        <Eyebrow>India&apos;s calling rules</Eyebrow>
                        <Heading>Made for TRAI&apos;s rules from day one.</Heading>
                        <Lead>Every call starts by saying it&apos;s automated and may be recorded. The agent only calls people who asked or agreed to be called, and stops when they say so.</Lead>
                    </div>
                    <div className="lg:pt-2"><Ticks items={[
                        "Opt-out phrases honoured at once, with a do-not-call list",
                        "Calling hours and days you set, holidays skipped",
                        "Follow-ups stop seven days after their last conversation, by default",
                        "Recordings and transcripts deleted on your schedule",
                        "Erase everything about a caller in one step",
                    ]} /></div>
                </Container>
            </Section>

            <PageFaq title="AI voice agent questions." faqs={FAQS} />
            <RelatedPages keys={["whatsapp", "website", "leads"]} />
            <FinalCTA />
        </SitePage>
    );
}
