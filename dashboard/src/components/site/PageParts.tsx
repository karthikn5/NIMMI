import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";
import { preload } from "react-dom";
import { ArrowRight, ArrowUpRight, Plus } from "lucide-react";
import JsonLd from "./JsonLd";
import { SiteFooter } from "./MoreSections";
import { Container, Eyebrow, Heading, PrimaryLink, Section, SecondaryLink } from "./primitives";
import RevealOnScroll from "./RevealOnScroll";
import SiteNav from "./SiteNav";
import { breadcrumbLd, faqLd, type Faq } from "@/lib/site/seo";
import "@/app/site-fonts.css";

/** The public site's pages beyond the home page (feature pages, pricing), built from the home page's own parts. */

export function SitePage({ children }: { children: ReactNode }) {
    preload("/fonts/inter-v20-latin.woff2", { as: "font", type: "font/woff2" });
    preload("/fonts/inter-tight-v9-latin.woff2", { as: "font", type: "font/woff2" });
    return (
        <div className="site-fonts min-h-screen bg-paper text-ink overflow-x-clip">
            <RevealOnScroll />
            <SiteNav />
            <main>{children}</main>
            <SiteFooter />
        </div>
    );
}

const rise = (ms: number) => ({ "--rise-delay": `${ms}ms` } as CSSProperties);

export function PageHero({ crumb, path, title, lead, secondary, note, preview }: {
    crumb: string; path: string; title: ReactNode; lead: ReactNode; secondary?: { href: string; label: string };
    note?: string; preview?: ReactNode;
}) {
    return (
        <section className="relative isolate pt-28 sm:pt-36 pb-16 sm:pb-24">
            {/* The home page's brand wash. */}
            <div aria-hidden className="absolute inset-0 -z-10" style={{
                background: [
                    "radial-gradient(70% 60% at 12% 0%, #ecdcf0 0%, rgba(236,220,240,0) 70%)",
                    "radial-gradient(55% 50% at 92% 8%, #f1e8f4 0%, rgba(241,232,244,0) 70%)",
                    "linear-gradient(180deg, #f4ecf6 0%, #f8f4f8 55%, #faf9f7 100%)",
                ].join(", "),
            }} />
            <JsonLd data={breadcrumbLd([["Home", "/"], [crumb, path]])} />
            <Container className={preview ? "grid lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] gap-14 lg:gap-12 items-center" : undefined}>
                <div>
                    <nav aria-label="Breadcrumb" className="site-rise mb-5">
                        <ol className="flex items-center gap-1.5 text-[13px] text-stone-500">
                            <li><Link href="/" className="hover:text-plum">Home</Link></li>
                            <li aria-hidden>/</li>
                            <li aria-current="page" className="text-stone-700">{crumb}</li>
                        </ol>
                    </nav>
                    <h1 className="site-rise font-display text-[38px] sm:text-[56px] leading-[1.04] font-medium tracking-[-0.03em] text-balance" style={rise(80)}>
                        {title}
                    </h1>
                    <p className="site-rise text-[18px] leading-relaxed text-stone-600 mt-6 max-w-xl" style={rise(180)}>{lead}</p>
                    <div className="site-rise flex flex-col sm:flex-row gap-3 mt-8" style={rise(260)}>
                        <PrimaryLink href="/auth/signup">Start free <ArrowRight size={16} /></PrimaryLink>
                        {secondary && <SecondaryLink href={secondary.href}>{secondary.label}</SecondaryLink>}
                    </div>
                    {note && <p className="site-rise text-[13px] text-stone-500 mt-5" style={rise(320)}>{note}</p>}
                </div>
                {preview && <div className="site-rise relative mx-auto w-full max-w-[460px] lg:max-w-none" style={rise(200)}>{preview}</div>}
            </Container>
        </section>
    );
}

/** A page's own questions, shown like the home page's FAQ and given to search engines as an FAQ. */
export function PageFaq({ title, faqs, tone = "white" }: { title: string; faqs: Faq[]; tone?: "white" | "paper" }) {
    return (
        <Section id="faq" tone={tone}>
            <JsonLd data={faqLd(faqs)} />
            <Container className="grid lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] gap-12">
                <div>
                    <Eyebrow>Questions</Eyebrow>
                    <Heading>{title}</Heading>
                    <p className="text-[15px] text-stone-600 mt-4">
                        Something else? Write to <a href="mailto:support.nimmi@gmail.com" className="text-plum hover:underline underline-offset-4">support.nimmi@gmail.com</a>.
                    </p>
                </div>
                <div className="border-t border-line">
                    {faqs.map((f) => (
                        <details key={f.q} className="group border-b border-line">
                            <summary className="flex items-center justify-between gap-4 py-5 cursor-pointer list-none text-[16px] font-medium [&::-webkit-details-marker]:hidden">
                                <h3 className="font-medium">{f.q}</h3>
                                <Plus size={18} className="shrink-0 text-stone-400 transition-transform group-open:rotate-45" aria-hidden />
                            </summary>
                            <p className="pb-5 -mt-1 text-[15px] leading-relaxed text-stone-600 max-w-2xl">{f.a}</p>
                        </details>
                    ))}
                </div>
            </Container>
        </Section>
    );
}

export const PAGES = {
    voice: { href: "/ai-voice-agent", name: "AI voice agent", text: "Answers your business calls, calls back leads and books appointments in 11 Indian languages." },
    whatsapp: { href: "/whatsapp-chatbot", name: "WhatsApp AI chatbot", text: "Replies on your WhatsApp Business number, understands voice notes and photos, and sends your files." },
    website: { href: "/ai-chatbot-for-website", name: "Website AI chatbot", text: "A custom chatbot trained on your website, PDFs and FAQs, live on your site with one line of code." },
    leads: { href: "/lead-management", name: "AI lead management", text: "Every lead scored hot, warm or cold, with call-backs, follow-ups and meetings handled for you." },
    pricing: { href: "/pricing", name: "Pricing", text: "Start free. Plans from ₹833 a month billed yearly, and call credits you buy as you need them." },
} as const;

/** Links to the other product pages: where a reader (and a crawler) goes next. */
export function RelatedPages({ keys, tone = "paper" }: { keys: (keyof typeof PAGES)[]; tone?: "white" | "paper" }) {
    return (
        <Section tone={tone} className="py-16 sm:py-20">
            <Container>
                <Eyebrow>Also in Nimmi</Eyebrow>
                <Heading className="sm:text-[34px]">One assistant for every channel.</Heading>
                <ul className="grid sm:grid-cols-2 lg:grid-cols-3 gap-px bg-line border border-line rounded-lg overflow-hidden mt-10">
                    {keys.map((k, i) => (
                        <li key={k} data-reveal style={{ "--reveal-delay": `${(i % 3) * 80}ms` } as CSSProperties} className="bg-white">
                            <Link href={PAGES[k].href} className="group block h-full p-6 hover:bg-stone-50 transition-colors">
                                <span className="inline-flex items-center gap-1 text-[15px] font-semibold group-hover:text-plum">
                                    {PAGES[k].name} <ArrowUpRight size={14} className="text-stone-400 group-hover:text-plum" />
                                </span>
                                <span className="block text-[14px] leading-relaxed text-stone-600 mt-1.5">{PAGES[k].text}</span>
                            </Link>
                        </li>
                    ))}
                </ul>
            </Container>
        </Section>
    );
}
