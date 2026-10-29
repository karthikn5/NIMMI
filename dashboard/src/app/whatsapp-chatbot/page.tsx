import type { Metadata } from "next";
import type { CSSProperties } from "react";
import JsonLd from "@/components/site/JsonLd";
import { FinalCTA } from "@/components/site/MoreSections";
import { PageFaq, PageHero, RelatedPages, SitePage } from "@/components/site/PageParts";
import { ChatPreview, LiveChatPreview, MemoryPreview, WhatsAppPreview } from "@/components/site/Previews";
import { Container, Eyebrow, Heading, Lead, Section } from "@/components/site/primitives";
import { Ticks } from "@/components/site/ProductSections";
import { pageMetadata, productLd, type Faq } from "@/lib/site/seo";

const PATH = "/whatsapp-chatbot";
const DESCRIPTION = "WhatsApp AI chatbot on your business number. It understands voice notes, photos and PDFs, sends brochures, captures leads and hands chats to your team.";

export const metadata: Metadata = pageMetadata({
    title: "WhatsApp AI Chatbot for Business in India",
    description: DESCRIPTION,
    path: PATH,
    image: "/og/whatsapp.png",
    keywords: ["WhatsApp chatbot", "WhatsApp AI chatbot", "WhatsApp AI agent", "WhatsApp Business API chatbot", "WhatsApp automation India",
               "WhatsApp auto reply", "WhatsApp bot for business", "WhatsApp lead generation", "WhatsApp customer support"],
});

const POINTS = [
    { title: "Waits until they finish", text: "Customers often send three short messages in a row. It waits for them to finish, then answers everything at once." },
    { title: "Shows that it's typing", text: "The “typing…” indicator and short messages, a few at a time, so it reads like a person and not a wall of text." },
    { title: "Understands voice notes", text: "Customers who'd rather talk send a voice note. It listens, in Tamil, Hindi, English and other Indian languages." },
    { title: "Reads photos and PDFs", text: "A form, a receipt, a product photo or a document: it reads what customers send and replies to it." },
    { title: "Sends your files", text: "Brochures, price lists, menus and photos from your files library, sent when they answer the question." },
    { title: "Offers quick replies", text: "Two or three buttons for common choices, so customers tap instead of typing." },
];

const FAQS: Faq[] = [
    { q: "What is a WhatsApp AI chatbot?", a: "It's an assistant that replies to your customers on WhatsApp, on your own business number. Nimmi's is trained on your business, so it answers questions, sends your brochures and price lists, takes enquiries and passes the chat to your team when needed." },
    { q: "Do I need the WhatsApp Business API?", a: "Nimmi works through Meta's official WhatsApp Business Platform, on your own number. You connect your number in WhatsApp > Settings in the dashboard, and the assistant starts answering." },
    { q: "Can it understand voice notes and photos?", a: "Yes. It listens to voice notes in Indian languages and English, reads photos and PDFs customers send, and replies to what's in them." },
    { q: "Can my team reply in the same chat?", a: "Yes. Your team answers from the WhatsApp inbox in the dashboard. When a person replies, the assistant steps back on that chat for a while, and you can hand it back any time." },
    { q: "Does it reply in Tamil and Hindi?", a: "Yes. It replies in the language and script the customer writes in. Tanglish and Hinglish written in English letters get replies the same way." },
    { q: "What does a WhatsApp chatbot cost?", a: "WhatsApp comes with the Growth plan, ₹2,499 a month or ₹2,083 a month billed yearly, with 10,000 AI replies a month. Meta's own charges apply to template messages you send outside WhatsApp's 24-hour window; replies to customers inside it are free." },
];

export default function WhatsAppChatbotPage() {
    return (
        <SitePage>
            <JsonLd data={productLd({ name: "Nimmi AI WhatsApp Chatbot", description: DESCRIPTION, path: PATH, lowPrice: "2083" })} />
            <PageHero
                crumb="WhatsApp chatbot" path={PATH}
                title={<>A WhatsApp AI chatbot that <span className="text-plum">replies like a person.</span></>}
                lead="Your assistant answers on your WhatsApp Business number, day and night. It understands voice notes, photos and PDFs, sends your brochures and price lists, and brings in your team when a customer needs a person."
                secondary={{ href: "/pricing", label: "See pricing" }}
                note="Works on Meta's official WhatsApp Business Platform, with your own number."
                preview={<WhatsAppPreview />}
            />

            <Section tone="white">
                <Container>
                    <Eyebrow>On WhatsApp</Eyebrow>
                    <Heading>Feels like chatting with your own staff.</Heading>
                    <Lead>People in India buy on WhatsApp. The assistant answers the way a good salesperson would: quickly, briefly, and in the customer&apos;s own language.</Lead>
                    <dl className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-8 mt-12">
                        {POINTS.map((p, i) => (
                            <div key={p.title} data-reveal style={{ "--reveal-delay": `${(i % 3) * 80}ms` } as CSSProperties} className="border-t border-line pt-4">
                                <dt className="text-[15px] font-semibold">{p.title}</dt>
                                <dd className="text-[14px] leading-relaxed text-stone-600 mt-1.5">{p.text}</dd>
                            </div>
                        ))}
                    </dl>
                </Container>
            </Section>

            <Section>
                <Container className="grid lg:grid-cols-2 gap-14 items-center">
                    <div className="order-2 lg:order-1"><ChatPreview /></div>
                    <div className="order-1 lg:order-2">
                        <Eyebrow>Leads and enquiries</Eyebrow>
                        <Heading>Turns WhatsApp enquiries into leads.</Heading>
                        <Lead>It answers the questions that come before a sale, then collects the details your team needs: name, budget, preferred date or anything you choose.</Lead>
                        <div className="mt-8"><Ticks items={[
                            "Your own details to collect, asked naturally, one at a time",
                            "Each lead scored hot, warm or cold",
                            "Lead alerts by email, and leads sent to your CRM",
                            "Tanglish and Hinglish understood and answered in kind",
                        ]} /></div>
                    </div>
                </Container>
            </Section>

            <Section tone="white">
                <Container className="grid lg:grid-cols-2 gap-14 items-center">
                    <div>
                        <Eyebrow>Your team</Eyebrow>
                        <Heading>Your team takes over in one tap.</Heading>
                        <Lead>WhatsApp chats and website chats land in one inbox. When a person replies, the assistant steps back on that chat, so customers never get two answers.</Lead>
                        <div className="mt-8"><Ticks items={[
                            "Internal notes your customers never see",
                            "Saved replies for the questions your team answers every day",
                            "Business hours, holidays and an away message",
                            "Hand the chat back to the assistant when you're done",
                        ]} /></div>
                    </div>
                    <LiveChatPreview />
                </Container>
            </Section>

            <Section>
                <Container className="grid lg:grid-cols-2 gap-14 items-center">
                    <div className="order-2 lg:order-1"><MemoryPreview /></div>
                    <div className="order-1 lg:order-2">
                        <Eyebrow>One memory</Eyebrow>
                        <Heading>Remembers them on every channel.</Heading>
                        <Lead>What a customer said on WhatsApp is known on their next call, and the other way round. Nobody has to explain twice.</Lead>
                    </div>
                </Container>
            </Section>

            <PageFaq title="WhatsApp chatbot questions." faqs={FAQS} />
            <RelatedPages keys={["voice", "website", "pricing"]} />
            <FinalCTA />
        </SitePage>
    );
}
