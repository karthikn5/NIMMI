import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { PAGES, SitePage } from "@/components/site/PageParts";
import { Container, PrimaryLink } from "@/components/site/primitives";

export const metadata = { title: "Page not found", robots: { index: false } };

export default function NotFound() {
    return (
        <SitePage>
            <section className="pt-36 pb-24">
                <Container>
                    <p className="text-[13px] font-medium text-plum mb-3">Page not found</p>
                    <h1 className="font-display text-[38px] sm:text-[52px] leading-[1.06] font-medium tracking-[-0.02em] max-w-2xl text-balance">
                        This page isn&apos;t here.
                    </h1>
                    <p className="text-[17px] leading-relaxed text-stone-600 mt-4 max-w-xl">The link may be old, or the address mistyped. These pages might be what you were looking for.</p>
                    <ul className="grid sm:grid-cols-2 lg:grid-cols-3 gap-px bg-line border border-line rounded-lg overflow-hidden mt-10">
                        {Object.values(PAGES).map((p) => (
                            <li key={p.href} className="bg-white">
                                <Link href={p.href} className="group block h-full p-6 hover:bg-stone-50 transition-colors">
                                    <span className="text-[15px] font-semibold group-hover:text-plum">{p.name}</span>
                                    <span className="block text-[14px] leading-relaxed text-stone-600 mt-1.5">{p.text}</span>
                                </Link>
                            </li>
                        ))}
                    </ul>
                    <PrimaryLink href="/" className="mt-10">Go to the home page <ArrowRight size={16} /></PrimaryLink>
                </Container>
            </section>
        </SitePage>
    );
}
