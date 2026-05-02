import Image from "next/image";

const services = [
  { image: "/service-ai.png", title: "AI Integration", desc: "Custom LLM-powered solutions tailored to your business needs and workflows." },
  { image: "/service-uiux.png", title: "Premium UI/UX", desc: "Design-first approach creating high-fidelity, interactive chat experiences." },
  { image: "/service-dev.png", title: "Custom Development", desc: "Full-stack development of robust, scalable chatbot applications." },
  { image: "/service-cart.png", title: "E-commerce Bots", desc: "Specialized shopping assistants that drive conversions and delight customers." },
  { image: "/chat-3d.png", title: "Multi-Platform", desc: "Deploy across web, mobile, WhatsApp, Telegram, and more seamlessly." },
  { image: "/gear-3d.png", title: "Custom Solutions", desc: "Bespoke integrations and architectures tailored to your unique vision." },
];

export default function Services() {
  return (
    <section id="services" className="py-16 sm:py-24 px-4 sm:px-6 bg-white relative overflow-hidden">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-10 sm:mb-16 relative">
          <span className="inline-block px-4 py-1.5 bg-purple-50 border border-purple-100 rounded-full text-sm font-medium text-[#9d55ac] mb-4">
            What We Offer
          </span>
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold mb-4">Our AI Chatbot Services</h2>
          <p className="text-zinc-500 max-w-xl mx-auto">Everything you need to build, launch, and scale your conversational AI business solutions.</p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6 sm:gap-6 relative">
          {services.map((s, i) => (
            <div key={i}
              className="p-6 sm:p-8 bg-[#faf9f7] rounded-3xl border border-zinc-100 hover:border-purple-200 hover:shadow-lg transition-all group cursor-default">
              <div className="w-16 h-16 rounded-2xl bg-purple-100 flex items-center justify-center mb-6 group-hover:bg-purple-200 transition-colors relative overflow-hidden">
                <Image 
                  src={s.image} 
                  alt={s.title} 
                  fill 
                  sizes="64px"
                  className="object-contain p-2 mix-blend-multiply" 
                  loading="lazy"
                />
              </div>
              <h3 className="text-lg font-bold mb-2">{s.title}</h3>
              <p className="text-sm text-zinc-500 leading-relaxed">{s.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
