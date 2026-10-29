import type { Metadata } from "next";
import type { CSSProperties } from "react";
import JsonLd from "@/components/site/JsonLd";
import { FinalCTA } from "@/components/site/MoreSections";
import { PageFaq, PageHero, RelatedPages, SitePage } from "@/components/site/PageParts";
import { CampaignPreview, DataPreview, MemoryPreview, SchedulePreview } from "@/components/site/Previews";
import { Container, Eyebrow, Heading, Lead, Section } from "@/components/site/primitives";
import { Ticks } from "@/components/site/ProductSections";
import { pageMetadata, productLd, type Faq } from "@/lib/site/seo";

const PATH = "/lead-management";
const DESCRIPTION = "Capture leads from calls, WhatsApp and your website, score them hot, warm or cold, and let AI call back, follow up and book meetings for your team.";

export const metadata: Metadata = pageMetadata({
    title: "AI Lead Management and Follow-up CRM",
    description: DESCRIPTION,
    path: PATH,
    image: "/og/leads.png",
    keywords: ["lead management software", "lead management tool", "AI CRM", "CRM for small business India", "lead follow-up automation",
               "lead scoring", "AI follow-up calls", "appointment booking software", "sales follow-up tool", "lead tracking"],
});

const FLOW = [
    { title: "Capture", text: "Every call, WhatsApp chat and website chat becomes a lead, with the details your team asked for: name, budget, location, date." },
    { title: "Score", text: "Each lead is rated hot, warm or cold, with the reason, whether the conversation met its goal and how the person felt." },
    { title: "Follow up", text: "Call-backs at the time people ask for, follow-ups by lead rating, and meetings you approve. The assistant makes the calls." },
    { title: "Close", text: "Your team gets the warm conversations: hot leads first, a brief before every transfer, and every lead in your CRM." },
];

const FAQS: Faq[] = [
    { q: "Is Nimmi a CRM?", a: "Nimmi is an AI lead management tool: it captures leads from calls, WhatsApp and your website, scores them, and follows up for you. It keeps a contact for every person with their calls, chats and notes. If you already use a CRM such as LeadSquared or Zoho, Nimmi sends every lead there." },
    { q: "How does AI lead scoring work?", a: "After every call or chat, the assistant rates the lead hot (ready to buy, book or visit soon), warm (interested, still deciding), cold (only asking) or not interested, and notes why. Your team can change any rating." },
    { q: "Can it follow up with leads automatically?", a: "Yes, when you turn it on. You set how many follow-ups each rating gets and how far apart. The assistant calls at about the hour the person last picked up, with what to say based on their last conversation, and stops when they book, say no or opt out." },
    { q: "Can it book meetings with my sales team?", a: "Yes. On the call it offers your free times and books one. You approve it, the assistant calls to confirm, and the person gets a reminder and the joining link before it starts. Missed meetings get a call to pick another time." },
    { q: "Can I send leads to my CRM?", a: "Yes. Leads go to your email, LeadSquared or Google Sheets, or by webhook to any CRM, Zapier, Make or Zoho Flow, as they happen. You can also export everything to CSV." },
    { q: "Are automated follow-up calls allowed in India?", a: "They are when the person asked or agreed to be contacted, as TRAI's rules require. The assistant says it's automated, honours opt-outs, keeps a do-not-call list, calls only in your calling hours, and by default stops following up seven days after their last conversation." },
];

export default function LeadManagementPage() {
    return (
        <SitePage>
            <JsonLd data={productLd({ name: "Nimmi AI Lead Management", description: DESCRIPTION, path: PATH })} />
            <PageHero
                crumb="Lead management" path={PATH}
                title={<>AI lead management <span className="text-plum">that follows up for you.</span></>}
                lead="Nimmi captures every lead from your calls, WhatsApp and website, scores it hot, warm or cold, then calls back, follows up and books meetings with your team. Nobody falls through the cracks."
                secondary={{ href: "/ai-voice-agent", label: "See the voice agent" }}
                note="Works on its own, or alongside the CRM you already use."
                preview={<SchedulePreview />}
            />

            <Section tone="white">
                <Container>
                    <Eyebrow>From first message to closed deal</Eyebrow>
                    <Heading>Every lead, from enquiry to meeting.</Heading>
                    <ol className="grid sm:grid-cols-2 lg:grid-cols-4 gap-10 lg:gap-8 mt-12">
                        {FLOW.map((s, i) => (
                            <li key={s.title} data-reveal style={{ "--reveal-delay": `${i * 90}ms` } as CSSProperties} className="border-t border-line-strong pt-5">
                                <span className="text-[13px] font-medium text-plum tabular-nums">Step {i + 1}</span>
                                <h3 className="font-display text-[20px] font-medium mt-2">{s.title}</h3>
                                <p className="text-[15px] leading-relaxed text-stone-600 mt-2">{s.text}</p>
                            </li>
                        ))}
                    </ol>
                </Container>
            </Section>

            <Section>
                <Container className="grid lg:grid-cols-2 gap-14 items-center">
                    <div className="order-2 lg:order-1"><DataPreview /></div>
                    <div className="order-1 lg:order-2">
                        <Eyebrow>Lead scoring</Eyebrow>
                        <Heading>Know which leads to call first.</Heading>
                        <Lead>Decide what the assistant should find out. After each conversation you get those details in a table, with a lead rating and whether it reached its goal.</Lead>
                        <div className="mt-8"><Ticks items={[
                            "Hot, warm, cold and not interested, with the reason",
                            "Filter your contacts by rating, and change any rating",
                            "The caller's mood and whether the call met its goal",
                            "Export to CSV, or send every lead to your CRM as it happens",
                        ]} /></div>
                    </div>
                </Container>
            </Section>

            <Section tone="white">
                <Container className="grid lg:grid-cols-2 gap-14 items-center">
                    <div>
                        <Eyebrow>Automatic follow-ups</Eyebrow>
                        <Heading>Follow-ups that know each lead.</Heading>
                        <Lead>The assistant writes what the next call should say from the last conversation, and calls at about the hour the person last picked up.</Lead>
                        <div className="mt-8"><Ticks items={[
                            "Your rules: how many follow-ups each rating gets, and how far apart",
                            "Call-backs booked on the call, at the time the person asks",
                            "A review step to check each follow-up before it's made",
                            "Stops when they book, say no, opt out or become a customer",
                        ]} /></div>
                    </div>
                    <MemoryPreview />
                </Container>
            </Section>

            <Section>
                <Container className="grid lg:grid-cols-2 gap-14 items-center">
                    <div className="order-2 lg:order-1"><CampaignPreview /></div>
                    <div className="order-1 lg:order-2">
                        <Eyebrow>Meetings and campaigns</Eyebrow>
                        <Heading>Book meetings, and call whole lists.</Heading>
                        <Lead>Meetings are booked on your free times and confirmed with a call. For a list of people who agreed to hear from you, run a campaign.</Lead>
                        <div className="mt-8"><Ticks items={[
                            "Meeting requests wait for your OK, then get a confirmation call",
                            "A reminder the day before, and the joining link before it starts",
                            "Campaigns with calling hours, retries and live progress",
                            "Results you can export, call by call",
                        ]} /></div>
                    </div>
                </Container>
            </Section>

            <PageFaq title="Lead management questions." faqs={FAQS} />
            <RelatedPages keys={["voice", "whatsapp", "pricing"]} />
            <FinalCTA />
        </SitePage>
    );
}
