import Navbar from "@/components/landing/Navbar";
import Hero from "@/components/landing/Hero";
import Features from "@/components/landing/Features";
import HowItWorks from "@/components/landing/HowItWorks";
import Services from "@/components/landing/Services";
import CTA from "@/components/landing/CTA";
import Footer from "@/components/landing/Footer";

export const metadata = {
  title: "Nimmi AI - Build Your Own Custom AI Chatbot | No Code Required",
  description: "Create, train, and deploy custom AI chatbots for your business in India. Train on your PDFs, website, or text documents. Embedded in minutes with Nimmi AI.",
  keywords: ["AI Chatbot India", "Custom AI Chatbot", "Chatbot Builder India", "No-code AI", "Business Chatbot"],
  openGraph: {
    title: "Nimmi AI - Build Your Own Custom AI Chatbot",
    description: "The most powerful no-code AI chatbot builder for Indian businesses.",
    url: "https://nimmiai.in",
    siteName: "Nimmi AI",
    images: [
      {
        url: "https://nimmiai.in/og-image.png",
        width: 1200,
        height: 630,
      },
    ],
    locale: "en_IN",
    type: "website",
  },
};

export default function Home() {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "Nimmi AI",
    "operatingSystem": "Web",
    "applicationCategory": "BusinessApplication",
    "offers": {
      "@type": "Offer",
      "price": "0",
      "priceCurrency": "USD"
    },
    "description": "Build custom AI chatbots for your business in India. Train on your data and embed anywhere.",
    "aggregateRating": {
      "@type": "AggregateRating",
      "ratingValue": "4.9",
      "reviewCount": "50"
    }
  };

  const orgJsonLd = {
    "@context": "https://schema.org",
    "@type": "Organization",
    "name": "Nimmi AI",
    "url": "https://nimmiai.in",
    "logo": "https://nimmiai.in/favicon.png",
    "sameAs": [
      "https://twitter.com/nimmiai",
      "https://linkedin.com/company/nimmiai"
    ]
  };

  const faqJsonLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
      {
        "@type": "Question",
        "name": "How do I build a custom AI chatbot with Nimmi AI?",
        "acceptedAnswer": {
          "@type": "Answer",
          "text": "You can build a custom AI chatbot by signing up for a Nimmi AI account, uploading your data (PDFs, URLs, or text), and using our no-code builder to design and deploy your assistant in minutes."
        }
      },
      {
        "@type": "Question",
        "name": "Can I train the AI on my own business data?",
        "acceptedAnswer": {
          "@type": "Answer",
          "text": "Yes, Nimmi AI is specifically designed to be trained on your own data. You can sync your website, upload documents, or provide raw text to create a chatbot that knows your business inside out."
        }
      },
      {
        "@type": "Question",
        "name": "Is there a free plan available?",
        "acceptedAnswer": {
          "@type": "Answer",
          "text": "Yes, Nimmi AI offers a free forever plan that allows you to build and test your first AI chatbot with basic features and limits."
        }
      }
    ]
  };

  return (
    <div className="min-h-screen bg-[#faf9f7] text-zinc-900 overflow-x-hidden">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(orgJsonLd) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqJsonLd) }}
      />

      <Navbar />
      <main>
        <Hero />
        <Features />
        <HowItWorks />
        <Services />
        <CTA />
      </main>
      <Footer />
    </div>
  );
}
