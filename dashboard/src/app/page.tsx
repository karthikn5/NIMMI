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
    "logo": "https://nimmiai.in/og-image.png",
    "sameAs": [
      "https://twitter.com/nimmiai",
      "https://linkedin.com/company/nimmiai"
    ]
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
      <LandingClient />
    </>
  );
}
