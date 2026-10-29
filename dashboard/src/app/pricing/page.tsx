import type { Metadata } from "next";
import JsonLd from "@/components/site/JsonLd";
import { FinalCTA, Pricing } from "@/components/site/MoreSections";
import { PageFaq, PageHero, RelatedPages, SitePage } from "@/components/site/PageParts";
import { pageMetadata, productLd, type Faq } from "@/lib/site/seo";

const PATH = "/pricing";
const DESCRIPTION = "Pricing for Nimmi's AI chatbot, WhatsApp chatbot and AI voice agent. Start free, then from ₹833 a month billed yearly. Call credits never expire.";

export const metadata: Metadata = pageMetadata({
    title: "Pricing for AI Chatbots and Voice Agents",
    description: DESCRIPTION,
    path: PATH,
    image: "/og/pricing.png",
    keywords: ["AI chatbot pricing India", "AI voice agent pricing", "AI calling cost per minute", "WhatsApp chatbot price",
               "chatbot subscription India", "voice bot pricing", "Nimmi AI pricing"],
});

const FAQS: Faq[] = [
    { q: "Is there a free plan?", a: "Yes. The free plan includes one assistant to build and test, one website published on a free address, and 10 call credits to try phone calls. You pay when you put an assistant live." },
    { q: "How do call credits work?", a: "A call minute is 1 credit for the voice, speech recognition and phone line, plus the rate of the AI model your agent uses. Calls are counted in half-minutes. Credits never expire." },
    { q: "How much does an AI phone call cost per minute?", a: "It depends on the AI model you choose for the agent. Quick models cost a little over 1 credit a minute; smarter ones cost more. At the 1,000-credit pack price of ₹4.50 a credit, a minute on a quick model is about ₹5. See the rate table above." },
    { q: "Are prices per assistant?", a: "Yes. Each assistant has its own plan, so an agency or a business with several brands pays for the assistants it puts live." },
    { q: "Can I pay monthly?", a: "Yes. Every plan can be paid monthly, and cancelled any time. Paying yearly gives you 12 months for the price of 10." },
    { q: "Are WhatsApp's own charges included?", a: "No. Meta charges separately for template messages you send outside WhatsApp's 24-hour window. Replies to customers inside the window are free." },
    { q: "Do you offer plans for agencies or larger teams?", a: "Yes. For many assistants, higher limits, custom voices or volume call pricing, write to support.nimmi@gmail.com and we'll put a plan together with you." },
];

export default function PricingPage() {
    return (
        <SitePage>
            <JsonLd data={productLd({ name: "Nimmi AI", description: DESCRIPTION, path: PATH })} />
            <PageHero
                crumb="Pricing" path={PATH}
                title={<>Pricing for AI chatbots <span className="text-plum">and voice agents.</span></>}
                lead="Start free with one assistant. Pick a plan when you put it live, and buy call credits only when you need them. Prices are per assistant, in rupees."
                secondary={{ href: "#rates", label: "See call rates" }}
            />
            <Pricing />
            <PageFaq title="Pricing questions." faqs={FAQS} />
            <RelatedPages keys={["voice", "whatsapp", "website"]} />
            <FinalCTA />
        </SitePage>
    );
}
