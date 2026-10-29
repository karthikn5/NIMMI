import type { Metadata } from "next";
import type { CSSProperties } from "react";
import JsonLd from "@/components/site/JsonLd";
import { FinalCTA } from "@/components/site/MoreSections";
import { PageFaq, PageHero, RelatedPages, SitePage } from "@/components/site/PageParts";
import { ChatPreview, DataPreview, LiveChatPreview } from "@/components/site/Previews";
import { Container, Eyebrow, Heading, Lead, Section } from "@/components/site/primitives";
import { Ticks } from "@/components/site/ProductSections";
import { pageMetadata, productLd, type Faq } from "@/lib/site/seo";

const PATH = "/ai-chatbot-for-website";
const DESCRIPTION = "Custom AI chatbot trained on your website, PDFs and FAQs. It answers visitors in 11 Indian languages, captures leads and hands over to your team. Free to start.";

export const metadata: Metadata = pageMetadata({
    title: "Custom AI Chatbot for Your Website",
    description: DESCRIPTION,
    path: PATH,
    image: "/og/website.png",
    keywords: ["custom AI chatbot", "AI chatbot for website", "chatbot builder", "no-code chatbot", "chatbot trained on your data",
               "website chat widget", "lead generation chatbot", "WordPress chatbot", "AI chatbot India", "GPT chatbot for website"],
});

const STEPS = [
    { title: "Teach it your business", text: "Add your website pages, PDFs, YouTube videos or a few FAQs, or start from an industry template and fill in the blanks." },
    { title: "Make it yours", text: "Your colours, your logo and your tone of voice. Add flows for forms and qualifying questions, with no code." },
    { title: "Put it on your website", text: "Paste one line of code on any website, or install the WordPress plugin. It's live in minutes." },
];

const FAQS: Faq[] = [
    { q: "What is a custom AI chatbot?", a: "A chatbot trained on your own business information, not a general one. It answers your visitors' questions from your website, documents and FAQs, in your tone, and collects the details your team needs." },
    { q: "How do I train the chatbot on my business?", a: "Add your website pages, PDFs, YouTube videos or plain text in the builder. When it can't answer a question, the question appears on your Questions page; answer it once and the chatbot uses your answer from then on." },
    { q: "Does it work with WordPress, Shopify or Wix?", a: "Yes. It works on any website where you can paste one line of code, and there's a WordPress plugin that adds it in a few clicks." },
    { q: "Will the chatbot make up answers?", a: "It answers only from the information you give it. When something isn't there, it says your team will follow up, and the question is saved for you to answer." },
    { q: "Can it capture leads from my website?", a: "Yes. You choose what it should find out, like name, phone number, budget or preferred date. Each lead is scored hot, warm or cold and sent to your email, CRM or a spreadsheet." },
    { q: "Can visitors talk to a person instead?", a: "Yes. Visitors can ask for a person at any time, and the chat moves to your team's Live chat. They can also ask for a call back instead of chatting." },
    { q: "How much does a website chatbot cost?", a: "You can build and test one assistant free. The Starter plan is ₹999 a month, or ₹833 a month billed yearly, with 2,000 AI replies a month." },
];

export default function WebsiteChatbotPage() {
    return (
        <SitePage>
            <JsonLd data={productLd({ name: "Nimmi AI Website Chatbot", description: DESCRIPTION, path: PATH })} />
            <PageHero
                crumb="Website chatbot" path={PATH}
                title={<>A custom AI chatbot, <span className="text-plum">trained on your business.</span></>}
                lead="Nimmi learns from your website, documents and FAQs, then answers your visitors in English, Hindi, Tamil and eight more Indian languages. It captures leads, books calls and hands the chat to your team when a person is needed."
                secondary={{ href: "/pricing", label: "See pricing" }}
                note="Free to build and test. One line of code to go live."
                preview={<ChatPreview />}
            />

            <Section tone="white">
                <Container>
                    <Eyebrow>How it works</Eyebrow>
                    <Heading>Build your chatbot this afternoon.</Heading>
                    <ol className="grid md:grid-cols-3 gap-10 md:gap-8 mt-12">
                        {STEPS.map((s, i) => (
                            <li key={s.title} data-reveal style={{ "--reveal-delay": `${i * 100}ms` } as CSSProperties} className="border-t border-line-strong pt-5">
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
                    <div>
                        <Eyebrow>Lead generation</Eyebrow>
                        <Heading>Every visitor question becomes a lead.</Heading>
                        <Lead>The chatbot answers first, then asks for the details your team needs, at the right moment. Leads arrive scored, so your team calls the right people first.</Lead>
                        <div className="mt-8"><Ticks items={[
                            "Your own fields: text, numbers, dates, yes or no, a list of choices",
                            "Hot, warm and cold leads, with whether the chat reached its goal",
                            "A call-back button for visitors who'd rather talk",
                            "Leads to your email, LeadSquared, Google Sheets or any CRM by webhook",
                        ]} /></div>
                    </div>
                    <DataPreview />
                </Container>
            </Section>

            <Section tone="white">
                <Container className="grid lg:grid-cols-2 gap-14 items-center">
                    <div className="order-2 lg:order-1"><LiveChatPreview /></div>
                    <div className="order-1 lg:order-2">
                        <Eyebrow>Live chat</Eyebrow>
                        <Heading>A person steps in when it matters.</Heading>
                        <Lead>When a visitor asks for a person, or is clearly unhappy, the chat moves to your team. They reply from one inbox for the website and WhatsApp.</Lead>
                        <div className="mt-8"><Ticks items={[
                            "Questions it couldn't answer are saved: answer once and it learns",
                            "Business hours, holidays and an away message",
                            "Owner, admin and agent roles for your staff",
                            "Chats and leads in 11 Indian languages",
                        ]} /></div>
                    </div>
                </Container>
            </Section>

            <PageFaq title="Website chatbot questions." faqs={FAQS} />
            <RelatedPages keys={["whatsapp", "voice", "leads"]} />
            <FinalCTA />
        </SitePage>
    );
}
