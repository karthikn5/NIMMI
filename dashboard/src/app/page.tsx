"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Bot, Zap, Shield, Wand2, ArrowRight, MessageSquare } from "lucide-react";
import { motion } from "framer-motion";
import Image from "next/image";
import Script from "next/script";

declare global {
  namespace JSX {
    interface IntrinsicElements {
      'spline-viewer': any;
    }
  }
}

export default function LandingPage() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <div className="min-h-screen bg-transparent text-zinc-900 selection:bg-blue-500/10 relative">
      <Script 
        src="https://unpkg.com/@splinetool/viewer@1.12.70/build/spline-viewer.js" 
        type="module" 
        strategy="afterInteractive"
      />

      {/* Spline Background Animation - Aggressively cropped to hide watermark */}
      {mounted && (
        <div className="fixed top-0 left-0 right-0 bottom-[-100px] z-0 pointer-events-none overflow-hidden">
          <spline-viewer 
            url="https://prod.spline.design/So3lziiUGo66NRnS/scene.splinecode"
            className="w-full h-full"
          ></spline-viewer>
        </div>
      )}

      {/* Full Transparency Overlays */}
      <div className="fixed inset-0 z-0 pointer-events-none bg-transparent transition-all" />
<style jsx global>{`
  spline-viewer {
    width: 100% !important;
    height: 100% !important;
  }
  /* Ensure the shadow dom footer/watermark is pushed out */
  spline-viewer #container {
    height: 100% !important;
  }
  /* Hide Spline logo badge */
  #spline-viewer-logo {
    display: none !important;
    visibility: hidden !important;
    opacity: 0 !important;
  }
`}</style>

      {/* Content Container (Ensure layout is relative/z-10) */}
      <div className="relative z-10 font-[family-name:var(--font-geist-sans)]">
        {/* Nav */}
      <nav className="fixed top-6 left-1/2 -translate-x-1/2 w-[calc(100%-3rem)] max-w-5xl z-50">
        <div className="bg-black/60 backdrop-blur-2xl border border-white/10 rounded-full px-8 h-16 flex items-center justify-between shadow-[0_8px_32px_rgba(0,0,0,0.3),inset_0_0_15px_rgba(255,255,255,0.05)] ring-1 ring-white/10">
          <div className="flex items-center gap-3 font-bold text-xl tracking-tighter">
            <div className="relative w-8 h-8 overflow-hidden rounded-full border border-white/20 shadow-inner bg-white/10">
              <Image
                src="/nimmi-logo.png"
                alt="Nimmi Logo"
                fill
                className="object-contain p-1 invert"
                priority
              />
            </div>
            <span className="bg-gradient-to-r from-white via-blue-400 to-zinc-400 bg-clip-text text-transparent drop-shadow-[0_1px_2px_rgba(0,0,0,0.5)]">Nimmi AI</span>
          </div>
          <div className="hidden md:flex items-center gap-8 text-white font-bold text-sm">
            <a href="#features" className="hover:text-blue-400 transition-colors relative group">
              Features
              <span className="absolute -bottom-1 left-0 w-0 h-0.5 bg-blue-400 transition-all group-hover:w-full"></span>
            </a>
            <a href="#how-it-works" className="hover:text-blue-400 transition-colors relative group">
              How it works
              <span className="absolute -bottom-1 left-0 w-0 h-0.5 bg-blue-400 transition-all group-hover:w-full"></span>
            </a>
            <a href="#pricing" className="hover:text-blue-400 transition-colors relative group">
              Pricing
              <span className="absolute -bottom-1 left-0 w-0 h-0.5 bg-blue-400 transition-all group-hover:w-full"></span>
            </a>
          </div>
          <Link href="/auth/login" className="px-6 py-2 bg-white text-black rounded-full text-sm font-bold hover:bg-zinc-200 transition-all shadow-lg shadow-white/10 hover:scale-105 active:scale-95">
            Get Started
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-40 pb-20 px-6">
        <div className="max-w-7xl mx-auto text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="inline-block relative max-w-5xl mx-auto"
          >
            <span className="inline-block px-4 py-1.5 rounded-full bg-blue-50/80 backdrop-blur-sm text-blue-600 text-sm font-semibold mb-6 border border-blue-100 shadow-sm">
              New: Gemini 1.5 Pro Support
            </span>
            <h1 className="text-5xl md:text-8xl font-bold tracking-tight mb-8 bg-gradient-to-b from-zinc-950 via-zinc-800 to-zinc-700 bg-clip-text text-transparent leading-tight drop-shadow-[0_4px_16px_rgba(255,255,255,1)]">
              Build your AI bot<br />in 5 minutes.
            </h1>
            <p className="text-xl text-zinc-950 max-w-2xl mx-auto font-bold mb-12 drop-shadow-[0_2px_8px_rgba(255,255,255,1)] leading-relaxed">
              The ultimate platform for creating custom-trained AI chatbots.
              Upload your documents, customize the look, and embed it anywhere.
            </p>
            
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link href="/auth/login" className="group px-8 py-4 bg-blue-600 text-white rounded-full font-bold text-lg hover:bg-blue-700 transition-all flex items-center gap-2 shadow-xl shadow-blue-500/20">
                Start Building Now
                <ArrowRight size={20} className="group-hover:translate-x-1 transition-transform" />
              </Link>
              <button className="px-8 py-4 bg-white/40 backdrop-blur-md text-zinc-900 border border-white/40 rounded-full font-bold text-lg hover:bg-white/60 transition-all">
                View Demo
              </button>
            </div>
          </motion.div>

          {/* Floating Preview */}
          <motion.div
            className="mt-24 relative"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.2, duration: 0.8 }}
          >
            <div className="absolute inset-0 bg-blue-400/10 blur-[120px] rounded-full mx-auto w-[60%] h-[60%]" />
            <div className="relative border border-white/40 rounded-3xl overflow-hidden shadow-2xl bg-white/30 backdrop-blur-xl aspect-[16/9] max-w-5xl mx-auto p-4 flex gap-4 ring-1 ring-white/20">
              {/* Dashboard Mockup */}
              <div className="w-1/4 h-full bg-zinc-50 rounded-xl border border-zinc-100 p-4 flex flex-col gap-4">
                {[1, 2, 3].map(i => <div key={i} className="h-8 w-full bg-zinc-200/50 rounded-lg" />)}
              </div>
              <div className="flex-1 h-full bg-zinc-50/50 rounded-xl border border-zinc-100 p-8 flex flex-col gap-6">
                <div className="h-12 w-1/3 bg-zinc-200/50 rounded-xl" />
                <div className="grid grid-cols-2 gap-4 flex-1">
                  <div className="bg-white rounded-2xl border border-zinc-100 shadow-sm" />
                  <div className="bg-white rounded-2xl border border-zinc-100 shadow-sm" />
                </div>
              </div>
              {/* Widget Preview */}
              <div className="absolute bottom-12 right-12 w-72 h-96 bg-white rounded-2xl shadow-2xl border border-zinc-100 flex flex-col overflow-hidden animate-bounce-slow">
                <div className="bg-blue-600 p-4 font-bold flex justify-between text-white">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-full bg-white/20 overflow-hidden relative">
                      <Image src="/nimmi-logo.png" alt="Logo" fill className="object-contain p-0.5" />
                    </div>
                    <span className="text-sm">AI Assistant</span>
                  </div>
                  <MessageSquare size={16} />
                </div>
                <div className="flex-1 p-4 flex flex-col gap-3">
                  <div className="bg-zinc-100 p-3 rounded-2xl rounded-tl-none text-xs w-3/4 text-zinc-700">Hello! How can I help you today?</div>
                  <div className="bg-blue-600 p-3 rounded-2xl rounded-tr-none text-xs w-2/3 self-end text-white">Can you explain the pricing?</div>
                </div>
                <div className="p-3 border-t border-zinc-100">
                  <div className="h-10 bg-zinc-50 rounded-xl border border-zinc-100 flex items-center px-3 text-[10px] text-zinc-400">Type a message...</div>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-24 px-6 border-t border-white/20 bg-white/10 backdrop-blur-lg">
        <div className="max-w-7xl mx-auto">
          <div className="grid md:grid-cols-3 gap-8">
            {[
              { icon: Zap, title: "Train in Seconds", desc: "Upload PDFs or link your website to instantly provide your AI with knowledge." },
              { icon: Wand2, title: "Fully Custom", desc: "Change colors, logos, and personality to match your brand's unique voice." },
              { icon: Shield, title: "Enterprise Grade", desc: "Advanced security and rate-limiting to keep your data and budget safe." },
            ].map((f, i) => (
              <div key={i} className="p-8 rounded-3xl bg-[#fcfcfd] border border-zinc-100 hover:border-blue-200 transition-all hover:shadow-lg hover:shadow-blue-500/5 group">
                <div className="w-12 h-12 bg-blue-50 rounded-2xl flex items-center justify-center mb-6 border border-blue-100 transition-transform group-hover:scale-110">
                  <f.icon className="text-blue-600" size={24} />
                </div>
                <h3 className="text-2xl font-bold mb-4 text-zinc-900">{f.title}</h3>
                <p className="text-zinc-600 leading-relaxed font-medium">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 border-t border-white/20 px-6 bg-white/10 backdrop-blur-md">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6 text-zinc-400 font-medium">
          <div className="flex items-center gap-3 font-bold text-lg text-zinc-900">
            <div className="relative w-8 h-8 overflow-hidden rounded-lg border border-zinc-100">
              <Image src="/nimmi-logo.png" alt="Logo" fill className="object-contain p-0.5" />
            </div>
            Nimmi AI
          </div>
          <p>© 2026 Nimmi AI. All rights reserved.</p>
        </div>
      </footer>
    </div>
  </div>
  );
}
