import type { Metadata } from "next";
import { preload } from "react-dom";
import Capabilities from "@/components/site/Capabilities";
import JsonLd from "@/components/site/JsonLd";
import RevealOnScroll from "@/components/site/RevealOnScroll";
import SiteNav from "@/components/site/SiteNav";
import {
  Channels, Connected, FollowUps, Hero, Insights, Memory, Outbound, Team, Tour, Voice, WhatsApp,
} from "@/components/site/ProductSections";
import { FAQ, FAQS, FinalCTA, HowItWorks, Industries, Integrations, Pricing, SiteFooter } from "@/components/site/MoreSections";
import { faqLd, organizationLd, pageMetadata, productLd, websiteLd } from "@/lib/site/seo";
import "./site-fonts.css";

const DESCRIPTION = "AI voice agent and chatbot that answers calls, WhatsApp and website chat in 11 Indian languages, captures leads, follows up and books meetings. Start free.";

export const metadata: Metadata = {
  ...pageMetadata({
    title: "AI Voice Agent, WhatsApp & Website Chatbot",
    description: DESCRIPTION,
    path: "/",
    keywords: ["AI voice agent", "AI calling agent", "WhatsApp chatbot", "AI chatbot for website", "custom AI chatbot", "AI receptionist",
               "AI telecaller", "lead management software", "AI CRM", "Tamil voice bot", "Hindi voice bot", "AI chatbot India", "Nimmi AI"],
  }),
  // The layout's "%s | Nimmi AI" template applies to pages below it, not to this one.
  title: { absolute: "AI Voice Agent, WhatsApp & Website Chatbot | Nimmi AI" },
};

export default function Home() {
  preload("/fonts/inter-v20-latin.woff2", { as: "font", type: "font/woff2" });
  preload("/fonts/inter-tight-v9-latin.woff2", { as: "font", type: "font/woff2" });
  return (
    <div className="site-fonts min-h-screen bg-paper text-ink overflow-x-clip">
      <RevealOnScroll />
      {/* Structured data mirrors what's on the page: the company, the site, the product and the FAQ shown below. */}
      <JsonLd data={[organizationLd, websiteLd, productLd({ name: "Nimmi AI", description: DESCRIPTION, path: "/" }), faqLd(FAQS)]} />
      <SiteNav />
      <main>
        <Hero />
        <Channels />
        <Tour />
        <Capabilities />
        <WhatsApp />
        <Voice />
        <Memory />
        <Outbound />
        <FollowUps />
        <Connected />
        <Insights />
        <Team />
        <HowItWorks />
        <Integrations />
        <Industries />
        <Pricing />
        <FAQ />
        <FinalCTA />
      </main>
      <SiteFooter />
    </div>
  );
}
