import Image from "next/image";

const features = [
  { image: "/feat-brain.png", title: "Natural Conversations", desc: "AI that understands context, tone, and intent — not just keywords." },
  { image: "/feat-design.png", title: "Beautiful Interfaces", desc: "Customizable chat widgets that match your brand perfectly." },
  { image: "/feat-rocket.png", title: "Lightning Setup", desc: "Go from idea to live chatbot in under 10 minutes." },
];

export default function Features() {
  return (
    <section id="about" className="py-16 sm:py-24 px-4 sm:px-6 bg-white">
      <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-10 md:gap-16 items-start">
        <div>
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold leading-tight mb-4">
            Why Business Teams Choose<br /><span className="text-[#9d55ac]">Nimmi AI</span>
          </h2>
          <p className="text-zinc-500 leading-relaxed mb-10 max-w-md">
            We don&apos;t just build bots. We craft intelligent, empathetic conversational experiences. Nimmi AI is the leading <strong>custom AI chatbot India</strong>-based platform for creating high-conversion assistants.
          </p>

          <div className="space-y-4">
            {features.map((f, i) => (
              <div key={i}
                className="flex items-start gap-4 p-5 bg-[#faf9f7] rounded-2xl border border-zinc-100 hover:border-purple-200 hover:shadow-md transition-all cursor-default">
                <div className="w-12 h-12 rounded-xl bg-purple-100 flex items-center justify-center shrink-0 relative overflow-hidden">
                  <Image 
                    src={f.image} 
                    alt={f.title} 
                    fill 
                    sizes="48px"
                    className="object-contain p-1.5 mix-blend-multiply" 
                    loading="lazy"
                  />
                </div>
                <div>
                  <h3 className="font-semibold text-zinc-900 mb-1">{f.title}</h3>
                  <p className="text-sm text-zinc-500 leading-relaxed">{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Chat Mockup - Static version for SEO */}
        <div className="relative scale-90 sm:scale-100 origin-top bg-white rounded-3xl shadow-xl border border-zinc-100 overflow-hidden">
          <div className="flex items-center gap-2 px-5 py-3 border-b border-zinc-100">
            <div className="w-3 h-3 rounded-full bg-red-400" />
            <div className="w-3 h-3 rounded-full bg-yellow-400" />
            <div className="w-3 h-3 rounded-full bg-green-400" />
          </div>
          <div className="p-6 space-y-4">
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-full bg-purple-100 shrink-0" />
              <div className="bg-zinc-100 rounded-2xl rounded-tl-md px-4 py-3 max-w-[80%]">
                <p className="text-sm text-zinc-700">Hi! How can I help you today? 😊</p>
              </div>
            </div>
            <div className="flex justify-end">
              <div className="bg-[#9d55ac] rounded-2xl rounded-tr-md px-4 py-3 max-w-[80%]">
                <p className="text-sm text-white">I want to set up a chatbot for my store</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-full bg-purple-100 shrink-0" />
              <div className="bg-zinc-100 rounded-2xl rounded-tl-md px-4 py-3 max-w-[80%]">
                <p className="text-sm text-zinc-700">Great choice! I can help with that. Let me walk you through — it only takes a few minutes ✨</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
