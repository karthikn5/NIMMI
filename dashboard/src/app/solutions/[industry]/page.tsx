import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, CheckCircle2, ShoppingCart, Stethoscope, Building2, ArrowRight, Zap, ShieldCheck, HeartPulse } from "lucide-react";

const industries = {
  "ecommerce": {
    title: "AI Chatbots for E-commerce",
    subtitle: "Turn visitors into loyal customers with 24/7 personalized shopping assistants.",
    icon: <ShoppingCart className="text-[#9d55ac]" size={48} />,
    heroImage: "/industry-ecommerce.png",
    benefits: [
      "Instant Cart Recovery: Remind users about their items.",
      "24/7 Customer Support: Resolve tracking and return queries instantly.",
      "Personalized Recommendations: Suggest products based on user intent.",
      "Seamless WhatsApp Integration: Sell where your customers chat."
    ],
    description: "Scale your online store in India with Nimmi AI. Our specialized e-commerce bots handle everything from size guides to order tracking, letting you focus on growth."
  },
  "healthcare": {
    title: "AI Chatbots for Healthcare",
    subtitle: "Improve patient engagement and streamline clinical workflows securely.",
    icon: <Stethoscope className="text-[#9d55ac]" size={48} />,
    heroImage: "/industry-healthcare.png",
    benefits: [
      "Automated Appointment Booking: Sync with your clinical calendar.",
      "Patient Triage: Direct patients to the right department based on symptoms.",
      "Secure FAQ Handling: Answer common medical and insurance questions.",
      "Post-Care Follow-ups: Send automated wellness checks and reminders."
    ],
    description: "Provide compassionate, instant support with HIPAA-compliant AI assistants. Nimmi AI helps hospitals and clinics in India provide better care through automation."
  },
  "real-estate": {
    title: "AI Chatbots for Real Estate",
    subtitle: "Capture high-intent leads and schedule site visits around the clock.",
    icon: <Building2 className="text-[#9d55ac]" size={48} />,
    heroImage: "/industry-realestate.png",
    benefits: [
      "24/7 Lead Capture: Never miss a property inquiry again.",
      "Virtual Tour Scheduling: Automate site visit bookings instantly.",
      "Property Matching: Filter listings based on budget and location.",
      "Instant Quote Generation: Provide basic pricing info on the spot."
    ],
    description: "Stay ahead in the competitive Indian real estate market. Our bots engage property seekers the moment they land on your site, qualifying leads while you sleep."
  }
};

export default function IndustryPage({ params }: { params: { industry: string } }) {
  const data = industries[params.industry as keyof typeof industries];

  if (!data) return <div className="p-20 text-center">Industry solution not found</div>;

  return (
    <div className="min-h-screen bg-white font-[family-name:var(--font-geist-sans)]">
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
                Get Started for {params.industry}
              </Link>
              <button className="px-8 py-4 border border-zinc-200 text-zinc-600 rounded-2xl font-bold text-lg hover:bg-zinc-50 transition-all text-center">
                View Live Demo
              </button>
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
              <p className="text-zinc-500">Go live with your industry-specific bot in under 10 minutes. No coding required.</p>
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
            <h2 className="text-3xl md:text-5xl font-bold mb-6">Ready to scale your {params.industry} business?</h2>
            <Link href="/auth/signup" className="inline-flex items-center gap-2 px-10 py-4 bg-[#9d55ac] text-white rounded-2xl font-bold text-xl hover:bg-[#8a4a97] transition-all shadow-2xl shadow-purple-500/30">
              Start Building Now <ArrowRight size={24} />
            </Link>
         </div>
      </section>

      {/* Footer */}
      <footer className="py-12 bg-white text-center border-t border-zinc-50">
        <p className="text-zinc-400 text-sm">© 2026 Nimmi AI. The leading AI solution for businesses in India.</p>
      </footer>
    </div>
  );
}
