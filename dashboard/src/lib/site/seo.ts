import type { Metadata } from "next";

/** Search and link-preview details for the public site (nimmiai.in). Every public page gets its own title, description
 * and canonical address from `pageMetadata`, so search engines see each page as itself, not as a copy of the home page. */

export const SITE = {
    name: "Nimmi AI",
    url: "https://nimmiai.in",
    email: "support.nimmi@gmail.com",
    logo: "https://nimmiai.in/favicon.png",
    instagram: "https://www.instagram.com/nimmiai.in",
    locale: "en_IN",
};

export function absolute(path: string) {
    return path.startsWith("http") ? path : `${SITE.url}${path === "/" ? "" : path}`;
}

export function pageMetadata({ title, description, path, image = "/og/home.png", type = "website", publishedTime, keywords }: {
    title: string;           // without the brand: the template adds " | Nimmi AI"
    description: string;     // 120-160 characters: what the page offers, in the searcher's words
    path: string;
    image?: string;          // 1200x630
    type?: "website" | "article";
    publishedTime?: string;
    keywords?: string[];
}): Metadata {
    const url = absolute(path);
    const full = `${title} | ${SITE.name}`;
    return {
        title,
        description,
        ...(keywords ? { keywords } : {}),
        alternates: { canonical: url },
        openGraph: {
            title: full, description, url, siteName: SITE.name, locale: SITE.locale, type,
            images: [{ url: image, width: 1200, height: 630, alt: title }],
            ...(publishedTime ? { publishedTime } : {}),
        },
        twitter: { card: "summary_large_image", title: full, description, images: [image] },
    };
}

/* ---------- Structured data (schema.org JSON-LD) ---------- */

export const organizationLd = {
    "@context": "https://schema.org",
    "@type": "Organization",
    "@id": `${SITE.url}/#organization`,
    name: SITE.name,
    url: SITE.url,
    logo: SITE.logo,
    email: SITE.email,
    description: "AI assistants for website chat, WhatsApp and phone calls in 11 Indian languages, built in India for Indian businesses.",
    areaServed: "IN",
    contactPoint: [{ "@type": "ContactPoint", contactType: "customer support", email: SITE.email, availableLanguage: ["English", "Hindi", "Tamil"] }],
    sameAs: [SITE.instagram],
};

export const websiteLd = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    "@id": `${SITE.url}/#website`,
    name: SITE.name,
    alternateName: ["Nimmi", "NimmiAI"],
    url: SITE.url,
    inLanguage: "en-IN",
    publisher: { "@id": `${SITE.url}/#organization` },
};

export function breadcrumbLd(trail: [string, string][]) {
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        itemListElement: trail.map(([name, path], i) => ({ "@type": "ListItem", position: i + 1, name, item: absolute(path) })),
    };
}

export type Faq = { q: string; a: string };

export function faqLd(faqs: Faq[]) {
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        mainEntity: faqs.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })),
    };
}

/** One of Nimmi's products, priced from the plans on the Pricing page (per assistant, INR). */
export function productLd({ name, description, path, lowPrice = "833", highPrice = "6999" }: {
    name: string; description: string; path: string; lowPrice?: string; highPrice?: string;
}) {
    return {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        name,
        description,
        url: absolute(path),
        applicationCategory: "BusinessApplication",
        operatingSystem: "Web",
        inLanguage: "en-IN",
        publisher: { "@id": `${SITE.url}/#organization` },
        offers: { "@type": "AggregateOffer", lowPrice, highPrice, priceCurrency: "INR", offerCount: 3, url: absolute("/pricing") },
    };
}

export function articleLd({ title, description, path, image, published, modified }: {
    title: string; description: string; path: string; image: string; published: string; modified?: string;
}) {
    return {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        headline: title,
        description,
        image: absolute(image),
        url: absolute(path),
        mainEntityOfPage: absolute(path),
        datePublished: published,
        dateModified: modified ?? published,
        inLanguage: "en-IN",
        author: { "@type": "Organization", name: `${SITE.name} Team`, url: SITE.url },
        publisher: { "@id": `${SITE.url}/#organization`, "@type": "Organization", name: SITE.name, logo: { "@type": "ImageObject", url: SITE.logo } },
    };
}
