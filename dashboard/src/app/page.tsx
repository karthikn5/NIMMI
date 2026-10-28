import type { Metadata } from "next";
import { preload } from "react-dom";
import Capabilities from "@/components/site/Capabilities";
import RevealOnScroll from "@/components/site/RevealOnScroll";
import SiteNav from "@/components/site/SiteNav";
import { Channels, Hero, Insights, Outbound, Team, Tour, Voice } from "@/components/site/ProductSections";
import { FAQ, FAQS, FinalCTA, HowItWorks, Industries, Integrations, Pricing, SiteFooter } from "@/components/site/MoreSections";
import "./site-fonts.css";

const TITLE = "Nimmi AI | AI assistant for website chat, WhatsApp and phone calls";
const DESCRIPTION = "An AI assistant trained on your business. It answers customers on your website, WhatsApp and phone in 11 Indian languages, captures leads, books appointments and hands over to your team. Free to build and test.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  keywords: ["AI chatbot India", "WhatsApp AI chatbot", "AI voice agent India", "AI phone receptionist", "custom AI chatbot", "Tamil Hindi voice bot", "lead capture chatbot"],
  alternates: { canonical: "https://nimmiai.in" },
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: "https://nimmiai.in",
    siteName: "Nimmi AI",
    images: [{ url: "https://nimmiai.in/og-image.png", width: 1200, height: 630 }],
    locale: "en_IN",
    type: "website",
  },
};

// Structured data mirrors what's on the page: the product, the company, and the FAQ shown below.
const softwareLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "Nimmi AI",
  operatingSystem: "Web",
  applicationCategory: "BusinessApplication",
  description: DESCRIPTION,
  offers: { "@type": "AggregateOffer", lowPrice: "999", highPrice: "6999", priceCurrency: "INR", offerCount: 3 },
};
const orgLd = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "Nimmi AI",
  url: "https://nimmiai.in",
  logo: "https://nimmiai.in/favicon.png",
  email: "support.nimmi@gmail.com",
  sameAs: ["https://www.instagram.com/nimmiai.in"],
};
const faqLd = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: FAQS.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })),
};

export default function Home() {
  preload("/fonts/inter-v20-latin.woff2", { as: "font", type: "font/woff2" });
  preload("/fonts/inter-tight-v9-latin.woff2", { as: "font", type: "font/woff2" });
  return (
    <div className="site-fonts min-h-screen bg-paper text-ink overflow-x-clip">
      <RevealOnScroll />
      {[softwareLd, orgLd, faqLd].map((ld, i) => (
        <script key={i} type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(ld) }} />
      ))}
      <SiteNav />
      <main>
        <Hero />
        <Channels />
        <Tour />
        <Capabilities />
        <Voice />
        <Outbound />
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
