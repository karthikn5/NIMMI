import { Check } from "lucide-react";
import Link from "next/link";

const plans = [
  {
    name: "Starter Plan",
    duration: "1 Month",
    originalPrice: "₹299",
    price: "₹99",
    monthlyEquivalent: "₹99/month",
    description: "Perfect for trying NIMMI AI",
    buttonText: "Get Started",
    badge: null,
    highlighted: false,
    features: [
      "1 Custom Chatbot",
      "Train on PDFs & Text",
      "Standard Response Time",
      "Basic Analytics",
      "Community Support"
    ]
  },
  {
    name: "Most Popular Plan",
    duration: "6 Months",
    originalPrice: "₹1499",
    price: "₹499",
    monthlyEquivalent: "₹83/month",
    description: "Best for regular users",
    buttonText: "Choose Plan",
    badge: "Most Popular",
    highlighted: true,
    features: [
      "1 Custom Chatbot",
      "Train on Website URLs",
      "Fast Response Time",
      "Advanced Analytics",
      "Priority Email Support",
      "Custom Widget Branding"
    ]
  },
  {
    name: "Best Value Plan",
    duration: "12 Months",
    originalPrice: "₹2599",
    price: "₹999",
    monthlyEquivalent: "₹83/month",
    description: "Save more with long-term access",
    buttonText: "Go Premium",
    badge: "Best Value",
    highlighted: false,
    features: [
      "1 Custom Chatbot",
      "Auto-Sync Data Source",
      "Lightning Fast API",
      "Export Chat Logs",
      "Dedicated Account Manager",
      "API Access"
    ]
  },
  {
    name: "Enterprise Plan",
    duration: "Custom",
    originalPrice: "",
    price: "Contact",
    monthlyEquivalent: "Custom",
    description: "For large scale businesses",
    buttonText: "Contact Us",
    badge: "Enterprise",
    highlighted: false,
    features: [
      "Unlimited Chatbots",
      "Custom AI Model Training",
      "White-label Solution",
      "24/7 Priority Support",
      "On-premise Deployment",
      "Custom Integrations"
    ]
  }
];

export default function Pricing() {
  return (
    <section id="pricing" className="py-16 sm:py-24 px-4 sm:px-6 relative overflow-hidden bg-[#faf9f7]">
      {/* Background glowing blobs */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-[#9d55ac] opacity-[0.03] blur-[100px] rounded-full pointer-events-none" />

      <div className="max-w-7xl mx-auto relative z-10">
        <div className="text-center mb-16">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-purple-50 border border-purple-100 rounded-full mb-6">
            <span className="text-sm font-semibold text-[#9d55ac]">Limited Time Offer</span>
          </div>
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold leading-tight mb-4 text-zinc-900">
            Simple, transparent pricing
          </h2>
          <p className="text-zinc-500 text-lg max-w-2xl mx-auto">
            Get early access pricing today. No hidden fees. Cancel anytime.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 items-stretch max-w-[90rem] mx-auto">
          {plans.map((plan, i) => (
            <div
              key={i}
              className={`relative flex flex-col p-8 rounded-3xl transition-all duration-300 backdrop-blur-md hover:-translate-y-2
                ${
                  plan.highlighted
                    ? "bg-white border-2 border-[#9d55ac] shadow-[0_0_40px_rgba(157,85,172,0.15)] md:scale-105 z-10"
                    : "bg-white/60 border border-zinc-200 shadow-xl shadow-zinc-200/20 hover:shadow-2xl hover:shadow-zinc-200/40"
                }
              `}
            >
              {plan.badge && (
                <div className={`absolute -top-4 left-1/2 -translate-x-1/2 px-5 py-1.5 rounded-full text-sm font-bold shadow-md whitespace-nowrap text-center
                  ${plan.highlighted ? "bg-[#9d55ac] text-white" : "bg-zinc-800 text-white"}
                `}>
                  {plan.badge}
                </div>
              )}

              <div className="mb-6">
                <h3 className="text-xl font-bold text-zinc-900 mb-1">{plan.name}</h3>
                <p className="text-sm font-medium text-zinc-500 mb-4">{plan.duration}</p>
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-lg text-zinc-400 line-through font-semibold">{plan.originalPrice}</span>
                  <span className="text-4xl font-bold text-zinc-900">{plan.price}</span>
                </div>
                <div className="flex items-center justify-between mt-2">
                  <p className="text-sm text-zinc-500">{plan.description}</p>
                  <p className="text-xs font-bold text-[#9d55ac] bg-purple-50 px-2 py-1 rounded-md">{plan.monthlyEquivalent}</p>
                </div>
              </div>

              <ul className="space-y-4 mb-8 flex-grow">
                {plan.features.map((feature, idx) => (
                  <li key={idx} className="flex items-start gap-3">
                    <Check size={18} className={`shrink-0 mt-0.5 ${plan.highlighted ? "text-[#9d55ac]" : "text-zinc-400"}`} />
                    <span className="text-zinc-600 text-sm">{feature}</span>
                  </li>
                ))}
              </ul>

              <Link
                href={plan.name === "Enterprise Plan" ? "#contact" : "/auth/signup"}
                className={`w-full py-3.5 px-6 rounded-xl font-semibold text-center transition-all duration-200 flex items-center justify-center gap-2
                  ${
                    plan.highlighted
                      ? "bg-gradient-to-r from-[#9d55ac] to-[#8a4a97] text-white shadow-lg shadow-[#9d55ac]/30 hover:shadow-[#9d55ac]/50 hover:opacity-90"
                      : "bg-white border-2 border-zinc-200 text-zinc-800 hover:border-[#9d55ac] hover:text-[#9d55ac]"
                  }
                `}
              >
                {plan.buttonText}
              </Link>
            </div>
          ))}
        </div>
        
        <p className="text-center text-zinc-400 text-sm mt-10">
          Need a custom enterprise solution? <Link href="#contact" className="text-[#9d55ac] font-medium hover:underline">Contact us</Link>
        </p>
      </div>
    </section>
  );
}
