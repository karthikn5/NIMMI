import type { Metadata } from "next";
import Link from "next/link";
import Image from "next/image";
import { notFound } from "next/navigation";
import { CheckCircle2, ShoppingCart, Stethoscope, Building2, ArrowRight, Zap, ShieldCheck, HeartPulse } from "lucide-react";
import JsonLd from "@/components/site/JsonLd";
import { breadcrumbLd, pageMetadata } from "@/lib/site/seo";

const industries = {
  "ecommerce": {
    title: "AI Chatbots for E-commerce",
    subtitle: "Turn visitors into loyal customers with 24/7 personalized shopping assistants.",
    icon: <ShoppingCart className="text-[#9d55ac]" size={48} />,
    heroImage: "/industry-ecommerce.png",
    benefits: [
      "Order Questions: Answer order status, returns and delivery queries from your own system.",
      "24/7 Customer Support: Website chat, WhatsApp and phone, in 11 Indian languages.",
      "Cash-on-Delivery Checks: Call customers to confirm COD orders before you ship.",
      "Seamless WhatsApp Integration: Sell where your customers chat, and send catalogues and price lists."
    ],
    description: "Scale your online store in India with Nimmi AI. Your assistant answers product questions, sizes and order status on your website, WhatsApp and phone, so your team can focus on growth."
  },
  "healthcare": {
    title: "AI Chatbots for Healthcare",
    subtitle: "Improve patient engagement and streamline clinical workflows securely.",
    icon: <Stethoscope className="text-[#9d55ac]" size={48} />,
    heroImage: "/industry-healthcare.png",
    benefits: [
      "Appointment Booking: Book consultations on your free slots, by phone, WhatsApp or chat.",
      "Doctor Timings and Departments: Answer where to go and when, never medical advice.",
      "Clinic FAQs: Fees, location, insurance accepted and what to bring, from your own information.",
      "Reminders and Follow-ups: A reminder before each appointment, and a call to rebook missed ones."
    ],
    description: "Answer every patient call and message, day and night. Nimmi AI helps hospitals and clinics in India book appointments and answer routine questions, and hands patients to your staff when needed."
  },
  "real-estate": {
    title: "AI Chatbots for Real Estate",
    subtitle: "Capture high-intent leads and schedule site visits around the clock.",
    icon: <Building2 className="text-[#9d55ac]" size={48} />,
    heroImage: "/industry-realestate.png",
    benefits: [
      "24/7 Lead Capture: Never miss a property enquiry again, on calls, WhatsApp or your website.",
      "Site Visit Booking: Book site visits on your free times, confirmed with a call.",
      "Project Answers: Prices, sizes and amenities from your own brochures and price lists.",
      "Lead Follow-ups: Calls back interested buyers and follows up until they decide."
    ],
    description: "Stay ahead in the competitive Indian real estate market. Your assistant engages property seekers the moment they enquire, on calls, WhatsApp or your website, qualifying leads while you sleep."
  }
};

// What each page is called in search results, with what people search for: chatbot, voice agent, WhatsApp.
const SEO: Record<string, { name: string; title: string; description: string }> = {
  "ecommerce": {
    name: "E-commerce", title: "AI Chatbot and Voice Agent for E-commerce",
    description: "AI chatbot, WhatsApp bot and voice agent for online stores in India: order status, returns, COD confirmation calls and product questions, 24/7.",
  },
  "healthcare": {
    name: "Healthcare", title: "AI Receptionist for Clinics and Hospitals",
    description: "AI receptionist for clinics and hospitals in India: books appointments, answers doctor timings and fees on calls, WhatsApp and chat, never medical advice.",
  },
  "real-estate": {
    name: "Real estate", title: "AI Chatbot and Voice Agent for Real Estate",
    description: "AI voice agent and chatbot for real estate in India: answers project enquiries, books site visits and follows up with buyers on calls, WhatsApp and web.",
  },
};

type Params = Promise<{ industry: string }>;

export function generateStaticParams() {
  return Object.keys(industries).map((industry) => ({ industry }));
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { industry } = await params;
  const seo = SEO[industry];
  if (!seo) return { title: "Not found", robots: { index: false } };
  return pageMetadata({ title: seo.title, description: seo.description, path: `/solutions/${industry}` });
}

export default async function IndustryPage({ params }: { params: Params }) {
  const { industry } = await params;
  const data = industries[industry as keyof typeof industries];

  if (!data) notFound();
  const seo = SEO[industry];

  return (
    <div className="min-h-screen bg-white font-[family-name:var(--font-geist-sans)]">
      <JsonLd data={breadcrumbLd([["Home", "/"], [seo.name, `/solutions/${industry}`]])} />
      {/* Navigation */}
      <nav className="p-6">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <Link href="/" className="relative h-10 w-28 flex items-center">
             <Image src="/nimmi-logo-new.png" alt="Nimmi AI" fill className="object-contain object-left scale-[2.5]" />
          </Link>
          <Link href="/auth/signup" className="px-6 py-2 bg-[#9d55ac] text-white rounded-xl font-bold hover:bg-[#8a4a97] transition-all">
            Start Free Trial
          </Link>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="py-20 px-6 overflow-hidden">
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
          <div>
            <div className="mb-6">{data.icon}</div>
            <h1 className="text-4xl md:text-6xl font-extrabold text-zinc-900 leading-tight mb-6">
              {data.title}
            </h1>
            <p className="text-xl text-zinc-500 mb-8 leading-relaxed">
              {data.subtitle}
            </p>
            <div className="flex flex-col sm:flex-row gap-4">
              <Link href="/auth/signup" className="px-8 py-4 bg-[#9d55ac] text-white rounded-2xl font-bold text-lg hover:bg-[#8a4a97] transition-all shadow-xl shadow-purple-500/20 text-center">
                Start free
              </Link>
              <Link href="/#how" className="px-8 py-4 border border-zinc-200 text-zinc-600 rounded-2xl font-bold text-lg hover:bg-zinc-50 transition-all text-center">
                See How It Works
              </Link>
            </div>
          </div>
          <div className="relative aspect-square lg:aspect-video w-full rounded-[3rem] bg-zinc-50 border border-zinc-100 overflow-hidden shadow-inner">
             {/* Fallback pattern */}
             <div className="absolute inset-0 bg-gradient-to-br from-purple-100/50 to-white flex items-center justify-center p-20">
                <div className="relative w-full h-full">
                   <Image src={data.heroImage} alt={data.title} fill className="object-contain drop-shadow-2xl" priority />
                </div>
             </div>
          </div>
        </div>
      </section>

      {/* Benefits Section */}
      <section className="py-24 bg-zinc-50 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">Why use Nimmi AI for your business?</h2>
            <p className="text-zinc-500 max-w-xl mx-auto">{data.description}</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {data.benefits.map((benefit, i) => (
              <div key={i} className="bg-white p-8 rounded-3xl border border-zinc-100 flex items-start gap-4 hover:shadow-lg transition-shadow">
                <CheckCircle2 className="text-green-500 shrink-0 mt-1" size={24} />
                <p className="text-lg font-medium text-zinc-700">{benefit}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Showcase */}
      <section className="py-24 px-6 bg-white">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-12 text-center">
           <div className="space-y-4">
              <div className="w-16 h-16 bg-purple-100 rounded-2xl flex items-center justify-center mx-auto mb-6">
                <Zap className="text-[#9d55ac]" />
              </div>
              <h3 className="text-xl font-bold">Fast Deployment</h3>
              <p className="text-zinc-500">Start from a template for your industry and go live the same day. No coding required.</p>
           </div>
           <div className="space-y-4">
              <div className="w-16 h-16 bg-purple-100 rounded-2xl flex items-center justify-center mx-auto mb-6">
                <ShieldCheck className="text-[#9d55ac]" />
              </div>
              <h3 className="text-xl font-bold">Secure & Private</h3>
              <p className="text-zinc-500">Your business data is encrypted and used only to train your specific assistant.</p>
           </div>
           <div className="space-y-4">
              <div className="w-16 h-16 bg-purple-100 rounded-2xl flex items-center justify-center mx-auto mb-6">
                <HeartPulse className="text-[#9d55ac]" />
              </div>
              <h3 className="text-xl font-bold">24/7 Availability</h3>
              <p className="text-zinc-500">Provide instant answers to your customers day and night, without hiring more staff.</p>
           </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-24 px-6 border-t border-zinc-100">
         <div className="max-w-4xl mx-auto text-center">
            <h2 className="text-3xl md:text-5xl font-bold mb-6">Ready to grow your {seo.name.toLowerCase()} business?</h2>
            <Link href="/auth/signup" className="inline-flex items-center gap-2 px-10 py-4 bg-[#9d55ac] text-white rounded-2xl font-bold text-xl hover:bg-[#8a4a97] transition-all shadow-2xl shadow-purple-500/30">
              Start Building Now <ArrowRight size={24} />
            </Link>
         </div>
      </section>

      {/* Footer */}
      <footer className="py-12 bg-white text-center border-t border-zinc-50">
        <p className="text-zinc-400 text-sm">© 2026 Nimmi AI. AI assistants for website chat, WhatsApp and phone calls, made in India.</p>
      </footer>
    </div>
  );
}
