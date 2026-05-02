import Link from "next/link";
import Image from "next/image";
import { ArrowRight, Sparkles, Play, Check, Bot } from "lucide-react";

export default function Hero() {
  return (
    <section id="home" className="pt-24 sm:pt-32 pb-12 sm:pb-20 px-4 sm:px-6">
      <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-8 md:gap-12 items-center">
        <div className="text-center md:text-left z-10">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-purple-50 border border-purple-100 rounded-full mb-8 mx-auto md:mx-0">
            <Sparkles size={14} className="text-[#9d55ac]" />
            <span className="text-sm font-medium text-[#9d55ac]">Your AI chatbot, your way</span>
          </div>

          <h1 className="text-3xl sm:text-5xl md:text-6xl lg:text-7xl font-bold leading-[1.1] mb-4 sm:mb-6">
            Build Your Own AI Chatbot — <br />
            <span className="text-[#9d55ac]">No Code Required</span>
          </h1>

          <div className="w-16 h-0.5 bg-zinc-300 mb-6 mx-auto md:mx-0" />

          <p className="text-zinc-500 text-base sm:text-lg leading-relaxed mb-6 sm:mb-8 max-w-lg mx-auto md:mx-0">
            Design, train, and deploy a <strong>custom AI chatbot for your website</strong> in India without writing a single line of code. Nimmi AI is the most powerful <strong>chatbot builder India</strong> has to offer for modern businesses.
          </p>

          <div className="flex flex-col sm:flex-row flex-wrap gap-3 sm:gap-4 mb-8 items-stretch sm:items-center">
            <Link href="/auth/signup"
              className="inline-flex items-center justify-center gap-2 px-5 sm:px-7 py-3 bg-[#9d55ac] text-white rounded-lg font-semibold hover:bg-[#8a4a97] transition-all shadow-lg shadow-[#9d55ac]/25 text-sm sm:text-base">
              Start Building Free <ArrowRight size={18} />
            </Link>
            <button className="inline-flex items-center justify-center gap-2 px-5 sm:px-7 py-3 bg-white border border-zinc-200 rounded-lg font-semibold text-zinc-700 hover:bg-zinc-50 transition-all shadow-sm text-sm sm:text-base">
              <Play size={16} /> Watch Demo
            </button>
          </div>

          <div className="flex flex-wrap items-center justify-center md:justify-start gap-4 sm:gap-6 text-sm text-zinc-500">
            <span className="flex items-center gap-1.5"><Check size={16} className="text-[#9d55ac]" /> No credit card</span>
            <span className="flex items-center gap-1.5"><Check size={16} className="text-[#9d55ac]" /> Free forever plan</span>
          </div>
        </div>

        <div className="relative flex items-center justify-center">
          {/* Floating badges - these can be static or animated with a small client component wrapper later */}
          <div className="absolute top-4 right-4 md:right-8 z-20 flex items-center gap-2 px-4 py-2 bg-white rounded-full shadow-lg border border-zinc-100">
            <Bot size={16} className="text-[#9d55ac]" />
            <span className="text-xs font-semibold text-zinc-700">AI Powered</span>
          </div>

          <div className="absolute bottom-12 left-4 md:left-8 z-20 flex items-center gap-2 px-4 py-2 bg-white rounded-full shadow-lg border border-zinc-100">
            <span className="text-[#9d55ac] font-bold text-sm">+</span>
            <span className="text-xs font-semibold text-zinc-700">Instant Setup</span>
          </div>

          <div className="relative w-[280px] h-[280px] sm:w-[320px] sm:h-[320px] md:w-[420px] md:h-[420px] mt-8 md:mt-0">
            <Image 
              src="/robot-mascot.png" 
              alt="AI Chatbot Mascot" 
              fill 
              sizes="(max-width: 768px) 280px, (max-width: 1200px) 420px, 420px"
              className="object-contain drop-shadow-2xl mix-blend-multiply" 
              priority 
              quality={90}
            />
          </div>
        </div>
      </div>
    </section>
  );
}
