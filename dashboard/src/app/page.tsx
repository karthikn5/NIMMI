import LandingClient from "./LandingClient";

// This is a Server Component (no "use client" here)
// Next.js will pre-render this on the server, ensuring 
// that search engine crawlers see the page content immediately.
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

  const websiteJsonLd = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    "name": "Nimmi AI",
    "url": "https://nimmiai.in"
  };

  return (
    <>
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
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteJsonLd) }}
      />
      <LandingClient />
    </>
  );
}
