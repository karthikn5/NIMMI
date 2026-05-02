import Image from "next/image";

const steps = [
  { num: "01", image: "/step-pencil.png", title: "Design Your Bot", desc: "Choose a template or start from scratch. Define your bot's personality, tone, and conversation flows with our visual builder." },
  { num: "02", image: "/feat-brain.png", title: "Train & Customize", desc: "Upload your knowledge base, FAQs, or documents. Fine-tune responses until your bot sounds exactly like your brand.", highlight: true },
  { num: "03", image: "/feat-rocket.png", title: "Deploy Anywhere", desc: "Embed on your website, connect to WhatsApp, Slack, or any platform. Go live with one click." },
];

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="py-16 sm:py-24 px-4 sm:px-6 bg-[#faf9f7]">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-16 relative">
          <span className="inline-block px-4 py-1.5 bg-purple-50 border border-purple-100 rounded-full text-sm font-medium text-[#9d55ac] mb-4">
            Simple Process
          </span>
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold mb-4">How to Build Your AI Chatbot</h2>
          <p className="text-zinc-500 max-w-xl mx-auto">Three simple steps to create your perfect AI chatbot in India. No coding, no complexity.</p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6 relative">
          {steps.map((s, i) => (
            <div key={i}
              className={`relative z-10 p-6 sm:p-8 rounded-3xl border transition-all hover:shadow-lg ${s.highlight ? "bg-purple-50 border-purple-200 shadow-md" : "bg-white border-zinc-100 hover:border-purple-100"
                }`}>
              <div className="absolute top-6 right-8 text-6xl font-bold text-zinc-100 select-none">{s.num}</div>
              <div className="w-16 h-16 rounded-2xl bg-purple-100 flex items-center justify-center mb-6 relative overflow-hidden">
                <Image 
                  src={s.image} 
                  alt={s.title} 
                  fill 
                  sizes="64px"
                  className="object-contain p-2 mix-blend-multiply" 
                  loading="lazy"
                />
              </div>
              <h3 className="text-xl font-bold mb-3">{s.title}</h3>
              <p className="text-sm text-zinc-500 leading-relaxed">{s.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
