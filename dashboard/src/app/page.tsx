"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { ArrowRight, MessageSquare, ChevronDown, Check, Star, Mail, User, Send, Sparkles, Palette, Smartphone, ShoppingBag, Globe, Zap, Shield, Users, BarChart2, Menu, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import Image from "next/image";

export default function LandingPage() {
  const [mounted, setMounted] = useState(false);
  const [activeFaq, setActiveFaq] = useState<number | null>(0);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return null;

  return (
    <div className="min-h-screen bg-white text-zinc-950 font-[family-name:var(--font-geist-sans)] selection:bg-blue-500/30 overflow-x-hidden">
      {/* Premium Background Pattern Layer */}
      <div 
        className="fixed inset-0 pointer-events-none z-[1] opacity-[0.15]" 
        style={{ 
          mixBlendMode: 'color-burn',
          backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%239C92AC' fill-opacity='0.1'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2v-4h4v-2h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2v-4h4v-2H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`,
        }}
      />
      {/* Navigation */}
      <nav className="fixed top-6 md:top-8 left-1/2 -translate-x-1/2 w-[95%] md:w-[90%] max-w-6xl z-50">
        <div className="bg-white/90 backdrop-blur-2xl border border-zinc-200/50 rounded-full px-4 md:px-8 py-2 md:py-3 flex items-center justify-between shadow-2xl relative overflow-hidden">
          {/* Logo Section */}
          <div className="flex items-center gap-2 relative z-10">
            <Link href="/" className="relative h-10 md:h-12 w-28 md:w-36 flex items-center">
              <Image 
                src="/nimmi-logo-new.png" 
                alt="Nimmi AI Logo" 
                fill
                className="object-contain scale-[2.8] origin-left translate-y-[-2px]"
                priority
              />
            </Link>
          </div>

          {/* Desktop Tabs */}
          <div className="hidden lg:flex items-center gap-8 xl:gap-10 absolute left-1/2 -translate-x-1/2">
            {["Home", "About", "How it Works", "Services"].map((item) => (
              <a key={item} href={`#${item.toLowerCase().replace(/\s+/g, '-')}`} className="text-sm font-semibold text-zinc-600 hover:text-zinc-950 transition-all hover:scale-105 active:scale-95">
                {item}
              </a>
            ))}
          </div>

          {/* Action Buttons & Mobile Toggle */}
          <div className="flex items-center gap-2 md:gap-4 relative z-10">
            <div className="hidden sm:flex items-center gap-4 mr-2">
              <Link href="/auth/login" className="text-sm font-bold text-zinc-950 hover:text-blue-600 transition-colors">Sign In</Link>
              <Link href="/auth/signup" className="px-5 md:px-6 py-2 md:py-2.5 bg-blue-600 text-white rounded-full text-sm font-black hover:bg-blue-700 transition-all shadow-lg shadow-blue-500/20 hover:scale-105 active:scale-95">
                Sign Up
              </Link>
            </div>
            
            {/* Mobile Menu Toggle */}
            <button 
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="p-2.5 bg-zinc-50 rounded-full border border-zinc-200 text-zinc-950 lg:hidden hover:bg-zinc-100 transition-colors"
              aria-label="Toggle Menu"
            >
              {isMobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation Menu */}
        <AnimatePresence>
          {isMobileMenuOpen && (
            <motion.div
              initial={{ opacity: 0, y: -20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -20, scale: 0.95 }}
              className="absolute top-full left-0 right-0 mt-4 lg:hidden"
            >
              <div className="mx-auto w-[98%] bg-white rounded-[2.5rem] border border-zinc-200/50 shadow-2xl p-6 md:p-8 backdrop-blur-3xl">
                <div className="flex flex-col gap-4">
                  {["Home", "About", "How it Works", "Services"].map((item) => (
                    <a 
                      key={item} 
                      href={`#${item.toLowerCase().replace(/\s+/g, '-')}`}
                      onClick={() => setIsMobileMenuOpen(false)}
                      className="text-2xl font-black text-zinc-950 tracking-tighter italic p-4 hover:bg-blue-50 rounded-2xl transition-all"
                    >
                      {item}
                    </a>
                  ))}
                  <div className="grid grid-cols-2 gap-4 mt-4 pt-6 border-t border-zinc-100 sm:hidden">
                    <Link 
                      href="/auth/login" 
                      onClick={() => setIsMobileMenuOpen(false)}
                      className="w-full py-4 text-center text-sm font-black text-zinc-950 bg-zinc-50 rounded-2xl border border-zinc-200"
                    >
                      Sign In
                    </Link>
                    <Link 
                      href="/auth/signup" 
                      onClick={() => setIsMobileMenuOpen(false)}
                      className="w-full py-4 text-center text-sm font-black text-white bg-blue-600 rounded-2xl shadow-lg shadow-blue-500/20"
                    >
                      Sign Up
                    </Link>
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </nav>

      {/* Hero Section */}
      <section id="home" className="relative pt-48 pb-40 px-6 overflow-hidden">
        {/* Background Asset */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-[45%] w-[1400px] h-[900px] opacity-100 pointer-events-none z-0">
          <Image 
            src="/hero-blur-v3.png" 
            alt="Gradient Glow" 
            fill 
            className="object-contain"
            priority
          />
        </div>
        
        {/* Subliminal Mesh Grid */}
        <div className="absolute inset-0 z-0 opacity-[0.03] pointer-events-none" 
          style={{ backgroundImage: 'radial-gradient(#000 1px, transparent 1px)', backgroundSize: '40px 40px' }} 
        />
        
        {/* 3D Star Asset */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-[45%] w-[800px] h-[800px] opacity-[0.03] pointer-events-none z-0">
          <Image 
            src="/star-3d.png" 
            alt="3D Star" 
            fill 
            className="object-contain"
          />
        </div>

        <div className="max-w-5xl mx-auto text-center relative z-10">
          <motion.h1 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-6xl md:text-9xl font-black tracking-tighter mb-8 leading-[0.9] text-zinc-950 italic"
          >
            Elevate Your <br />
            Brand with AI.
          </motion.h1>
          
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="text-zinc-500 text-lg md:text-2xl font-semibold mb-12 max-w-3xl mx-auto leading-relaxed"
          >
            Nimmi AI is a premium design & development agency specializing in <br className="hidden md:block" />
            custom-trained AI solutions, high-end UI/UX, and future-proof digital products.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="flex flex-col md:flex-row items-center justify-center gap-6"
          >
            <Link href="/auth/login" className="px-12 py-5 bg-blue-600 text-white rounded-2xl font-black text-xl hover:bg-blue-700 transition-all shadow-[0_10px_40px_rgba(37,99,235,0.3)] hover:scale-105 active:scale-95">
              Start Your Project
            </Link>
            <a href="#services" className="px-12 py-5 bg-white border-2 border-zinc-100 text-zinc-950 rounded-2xl font-black text-xl hover:bg-zinc-50 transition-all shadow-xl hover:scale-105 active:scale-95">
              View Our Work
            </a>
          </motion.div>
        </div>
      </section>
      {/* About Section */}
      <section id="about" className="py-24 px-6 relative z-10 border-t border-zinc-100 overflow-hidden">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center gap-20">
          <div className="flex-1 space-y-10">
            <h2 className="text-5xl md:text-8xl font-black text-zinc-950 tracking-tighter italic leading-[0.9]">
              Elite AI <br /> Engineering.
            </h2>
            <p className="text-zinc-500 text-xl font-semibold leading-relaxed max-w-xl">
              At Nimmi AI, we don't just build software. We engineer intelligent experiences that define the next generation of brand-customer interaction. Our team combines high-end aesthetics with cutting-edge machine learning.
            </p>
            <div className="flex items-center gap-10">
              <div>
                <p className="text-4xl font-black text-blue-600 tracking-tighter italic">99%</p>
                <p className="text-xs font-black uppercase tracking-widest text-zinc-400 mt-1">Client Satisfaction</p>
              </div>
              <div>
                <p className="text-4xl font-black text-purple-600 tracking-tighter italic">50+</p>
                <p className="text-xs font-black uppercase tracking-widest text-zinc-400 mt-1">AI Projects Live</p>
              </div>
            </div>
          </div>
          <div className="flex-1 relative">
            <div className="aspect-square rounded-[4rem] bg-zinc-100 border border-zinc-200/50 relative overflow-hidden group shadow-2xl">
              <Image 
                src="/about-realistic.png" 
                alt="AI Engineering Workspace" 
                fill 
                className="object-cover group-hover:scale-105 transition-transform duration-1000" 
              />
              <div className="absolute inset-0 bg-blue-600/10 opacity-0 group-hover:opacity-100 transition-opacity" />
              {/* Floating Logo Overlay */}
              <div className="absolute bottom-10 right-10 w-24 h-24 bg-white/40 backdrop-blur-xl rounded-2xl border border-white/40 flex items-center justify-center p-4 shadow-xl translate-y-4 opacity-0 group-hover:translate-y-0 group-hover:opacity-100 transition-all duration-500">
                 <Image src="/nimmi-logo-3d.png" alt="Nimmi AI" width={80} height={80} className="object-contain" />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* How it Works Section */}
      <section id="how-it-works" className="py-24 px-6 relative z-10 bg-zinc-950 text-white overflow-hidden">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-24">
            <h2 className="text-5xl md:text-8xl font-black tracking-tighter italic mb-6">How We Build.</h2>
            <p className="text-zinc-400 text-xl font-medium max-w-2xl mx-auto">Our streamlined process ensures your vision is executed with surgical precision and artistic flair.</p>
          </div>
          
          <div className="grid md:grid-cols-3 gap-12 relative z-10">
            {[
              { step: "01", title: "Strategy Audit", desc: "We deep-dive into your business goals and AI opportunities." },
              { step: "02", title: "Custom Engineering", desc: "Bespoke development with continuous synchronization." },
              { step: "03", title: "Scale & Optimize", desc: "Launch and iterative improvements for maximum impact." },
            ].map((s, i) => (
              <div key={i} className="group relative">
                <div className="text-[10rem] font-black text-white/5 absolute -top-20 -left-6 leading-none select-none tracking-tighter">{s.step}</div>
                <div className="relative z-10 space-y-6">
                  <div className="w-16 h-2 bg-blue-600 group-hover:w-32 transition-all duration-500" />
                  <h3 className="text-3xl font-black italic tracking-tighter">{s.title}</h3>
                  <p className="text-zinc-400 font-medium leading-relaxed">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
        
        {/* Decorative Grid for Dark Mode */}
        <div className="absolute inset-0 opacity-[0.05] pointer-events-none" 
          style={{ backgroundImage: 'radial-gradient(#fff 1px, transparent 1px)', backgroundSize: '60px 60px' }} 
        />
        <div className="absolute -bottom-1/2 -right-1/4 w-[1000px] h-[1000px] bg-blue-600/10 blur-[200px] rounded-full" />
      </section>

      {/* Services Section */}
      <section id="services" className="py-24 px-6 relative z-10 bg-slate-50/50 backdrop-blur-3xl border-t border-zinc-100">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-5xl md:text-7xl font-black mb-20 text-zinc-950 tracking-tighter italic">Our Services</h2>
          <div className="grid md:grid-cols-4 gap-6 mb-6">
            {[
              { title: "AI Integration", iconPath: "/icons/ai-realistic.png", desc: "We build custom LLM-powered solutions tailored to your business needs and workflows." },
              { title: "Premium UI/UX", iconPath: "/icons/design-realistic.png", desc: "Design-first approach creating high-fidelity, interactive experiences that wow your users." },
              { title: "Custom Software", iconPath: "/icons/software-realistic.png", desc: "Full-stack development of robust, scalable applications using modern tech stacks." },
              { title: "E-comm Mastery", iconPath: "/icons/ecomm-3d.png", desc: "Specialized e-commerce solutions that drive conversions and enhance brand loyalty." },
            ].map((service, i) => (
              <div key={i} className="p-10 rounded-[3rem] bg-white border border-zinc-200/50 hover:border-blue-500/30 transition-all group overflow-hidden relative shadow-sm hover:shadow-2xl hover:-translate-y-2 duration-500">
                <div className={`w-28 h-28 rounded-2xl bg-zinc-50/50 flex items-center justify-center mb-10 group-hover:bg-blue-50 transition-all duration-500 relative overflow-hidden`}>
                  <Image 
                    src={service.iconPath} 
                    alt={service.title} 
                    fill 
                    className="object-contain p-2 group-hover:scale-110 transition-transform duration-500" 
                  />
                </div>
                <h3 className="text-2xl font-black mb-4 text-zinc-950 tracking-tight">{service.title}</h3>
                <p className="text-zinc-500 text-sm leading-relaxed font-semibold">
                  {service.desc}
                </p>
                <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 blur-[80px] rounded-full translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
            ))}
          </div>
          <div className="grid md:grid-cols-2 gap-6">
            <div className="p-10 rounded-[3rem] bg-white border border-zinc-200/50 hover:border-blue-500/30 transition-all group overflow-hidden relative shadow-sm hover:shadow-2xl flex items-center gap-10 duration-500">
                <div className="w-40 h-40 rounded-3xl bg-zinc-50 flex items-center justify-center shrink-0 relative overflow-hidden group-hover:bg-blue-50 transition-colors duration-500 shadow-inner">
                   <Image 
                    src="/icons/webflow-3d.png" 
                    alt="Webflow Mastery" 
                    fill 
                    className="object-contain p-6 group-hover:scale-110 transition-transform duration-500" 
                  />
                </div>
                <div className="relative z-10 flex-1">
                  <h3 className="text-3xl font-black mb-3 text-zinc-950 tracking-tighter italic">Webflow Mastery</h3>
                  <p className="text-zinc-500 text-sm leading-relaxed font-semibold">
                    We specialize in Webflow development, delivering ultra-fast, pixel-perfect, and responsive digital experiences.
                  </p>
                </div>
                <div className="absolute -bottom-10 -right-10 w-40 h-40 bg-blue-500/5 blur-[60px] rounded-full group-hover:bg-blue-500/10 transition-all" />
            </div>
            <div className="p-10 rounded-[3rem] bg-white border border-zinc-200/50 hover:border-blue-500/30 transition-all group overflow-hidden relative shadow-sm hover:shadow-2xl flex items-center gap-10 duration-500">
                <div className="w-40 h-40 rounded-3xl bg-zinc-50 flex items-center justify-center shrink-0 relative overflow-hidden group-hover:bg-blue-50 transition-colors duration-500 shadow-inner">
                   <Image 
                    src="/icons/software-3d.png" 
                    alt="Custom Development" 
                    fill 
                    className="object-contain p-4 group-hover:scale-110 transition-transform duration-500" 
                  />
                </div>
                <div className="relative z-10 flex-1">
                  <h3 className="text-3xl font-black mb-3 text-zinc-950 tracking-tighter italic">Custom Solutions</h3>
                  <p className="text-zinc-500 text-sm leading-relaxed font-semibold">
                    Building complex integrations, bespoke features, and scalable backend architectures tailored to your vision.
                  </p>
                </div>
                <div className="absolute -bottom-10 -right-10 w-40 h-40 bg-blue-500/5 blur-[60px] rounded-full group-hover:bg-blue-500/10 transition-all" />
            </div>
          </div>
        </div>
      </section>

      {/* Portfolio Section */}
      <section id="portfolio" className="py-24 px-6 relative border-t border-zinc-100">
        <div className="max-w-7xl mx-auto text-center">
          <h2 className="text-4xl md:text-5xl font-black mb-4 text-zinc-950">Check our Work</h2>
          <p className="text-zinc-500 mb-16 font-medium">Explore our latest projects and see how we help our clients grow.</p>
          
          <div className="grid md:grid-cols-3 gap-10">
            {[
              { name: "Nimmi AI Dashboard", category: "AI & Platform", img: "/portfolio/ai-dashboard.png" },
              { name: "SaaS Analytics Pro", category: "Data Vis", img: "/portfolio/saas-analytics.png" },
              { name: "E-commerce Redesign", category: "UI/UX", img: "/portfolio/ecommerce-app.png" },
            ].map((item, i) => (
              <div key={i} className="rounded-[50px] overflow-hidden group relative aspect-[4/5] bg-white border border-zinc-200/50 shadow-sm hover:shadow-[0_20px_60px_rgba(37,99,235,0.15)] transition-all duration-700">
                <div className="absolute inset-0 bg-gradient-to-t from-zinc-950/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity z-10" />
                <div className="absolute bottom-0 left-0 right-0 p-12 translate-y-8 group-hover:translate-y-0 transition-all duration-500 z-20">
                   <div className="text-white text-left">
                     <p className="font-black text-4xl mb-3 tracking-tighter italic">{item.name}</p>
                     <p className="text-[10px] text-white/60 uppercase tracking-[0.3em] font-black">{item.category}</p>
                   </div>
                </div>
                
                {/* Visual Representation - Now with Actual Images */}
                <div className="w-full h-full relative overflow-hidden transition-transform duration-1000 group-hover:scale-110">
                   <Image 
                    src={item.img} 
                    alt={item.name} 
                    fill 
                    className="object-cover" 
                  />
                  {/* Glass Overlay on Hover */}
                  <div className="absolute inset-0 bg-white/5 backdrop-blur-[2px] opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section id="pricing" className="py-24 px-6 border-t border-zinc-100">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row gap-8 items-stretch">
          <div className="flex-1 p-12 rounded-[40px] bg-zinc-950 border border-zinc-800 shadow-2xl flex flex-col justify-between relative overflow-hidden group">
            <div className="relative z-10">
              <h2 className="text-4xl font-black mb-8 text-white tracking-tighter italic">Enterprise</h2>
              <p className="text-zinc-400 font-bold text-3xl mb-12 leading-tight">Custom AI <br /> Development</p>
              <p className="text-zinc-500 text-sm font-medium mb-12">Tailored solutions for large-scale deployments and complex integrations.</p>
            </div>
            <Link href="/auth/login" className="relative z-10 px-8 py-4 bg-white text-zinc-950 rounded-xl font-black hover:bg-zinc-100 transition-all self-start shadow-xl active:scale-95">
              Contact Sales
            </Link>
            <div className="absolute top-0 right-0 w-64 h-64 bg-blue-600/10 blur-[100px] rounded-full" />
          </div>
          <div className="flex-[1.5] p-12 rounded-[40px] bg-white border border-zinc-200/50 shadow-2xl relative overflow-hidden">
             <div className="relative z-10">
                <div className="flex justify-between items-start mb-10">
                  <div>
                    <h3 className="text-3xl font-black text-zinc-950 tracking-tighter italic">Scale Plan</h3>
                    <p className="text-zinc-500 text-sm font-bold mt-1">Best for growing startups</p>
                  </div>
                  <div className="text-right">
                    <p className="text-6xl font-black text-zinc-950 tracking-tighter">$4,950<span className="text-lg text-zinc-400 font-bold tracking-tight">/mo</span></p>
                  </div>
                </div>
                <div className="space-y-6 mb-12 grid grid-cols-2 gap-x-12">
                   {[
                     { name: "Custom LLM Training", icon: Zap },
                     { name: "Priority Support", icon: Shield },
                     { name: "Dedicated Designer", icon: Palette },
                     { name: "Advanced Analytics", icon: BarChart2 },
                     { name: "Unlimited Requests", icon: Users },
                     { name: "Weekly Sync Calls", icon: Globe }
                   ].map((feature) => (
                     <div key={feature.name} className="flex items-center gap-3">
                       <Check size={18} className="text-blue-500 shrink-0" />
                       <span className="text-sm font-bold text-zinc-600">{feature.name}</span>
                     </div>
                   ))}
                </div>
                <Link href="/auth/login" className="block w-full py-6 bg-blue-600 text-white text-center rounded-2xl font-black text-xl hover:bg-blue-700 transition-all shadow-[0_10px_30px_rgba(37,99,235,0.2)] active:scale-[0.99]">
                  Get Started Now
                </Link>
             </div>
             <div className="absolute bottom-0 right-0 w-[500px] h-[500px] bg-blue-500/5 blur-[150px] rounded-full" />
          </div>
        </div>
      </section>

      {/* FAQ Section */}
      <section id="faq" className="py-24 px-6 relative overflow-hidden border-t border-zinc-100">
        <div className="absolute top-1/2 left-0 w-[500px] h-[500px] bg-blue-600/5 blur-[120px] rounded-full -translate-x-1/2" />
        
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row gap-20">
          <div className="flex-1">
            <h2 className="text-5xl font-black mb-12 leading-tight text-zinc-950">Frequently <br /> Asked <br /> Questions</h2>
            <div className="w-48 h-48 relative opacity-10">
               <div className="absolute inset-0 border border-zinc-300 rounded-full animate-[spin_20s_linear_infinite]" />
               <div className="absolute inset-4 border border-zinc-400 rounded-full animate-[spin_25s_linear_infinite_reverse]" />
            </div>
          </div>
          <div className="flex-[1.5] space-y-4">
            {[
              "How does custom AI integration work?",
              "Do you provide ongoing support?",
              "What is the typical project timeline?",
              "Can you help with existing product redesigns?"
            ].map((q, i) => (
              <div key={i} className="bg-white border border-zinc-200/50 rounded-3xl overflow-hidden shadow-sm transition-colors hover:bg-slate-50">
                <button 
                  onClick={() => setActiveFaq(activeFaq === i ? null : i)}
                  className="w-full px-8 py-7 flex items-center justify-between font-bold text-left transition-colors"
                >
                  <span className={activeFaq === i ? "text-zinc-950" : "text-zinc-500"}>{q}</span>
                  <ChevronDown className={`transition-transform duration-300 ${activeFaq === i ? 'rotate-180 text-zinc-950' : 'text-zinc-400'}`} />
                </button>
                <AnimatePresence>
                  {activeFaq === i && (
                    <motion.div 
                      initial={{ height: 0 }}
                      animate={{ height: "auto" }}
                      exit={{ height: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="px-8 pb-8 text-zinc-600 leading-relaxed text-sm font-medium">
                        We take a deep dive into your business processes, identify high-impact AI opportunities, and build custom models or integrations that scale with your brand. From initial audit to final deployment, we handle the technical heavy lifting while you focus on growth.
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Contact Section */}
      <section id="contact" className="py-24 px-6 relative border-t border-zinc-100">
        <div className="max-w-6xl mx-auto">
          <div className="bg-white rounded-[50px] p-20 border border-zinc-200/50 relative overflow-hidden text-center backdrop-blur-3xl shadow-2xl">
            <h2 className="text-5xl font-black mb-16 text-zinc-950">Let's Get in Touch</h2>
            <div className="max-w-2xl mx-auto relative z-10">
              <div className="space-y-8">
                <div className="grid md:grid-cols-2 gap-8">
                  <div className="text-left">
                    <label className="block text-xs uppercase tracking-widest font-black text-zinc-500 mb-4 ml-2">Name</label>
                    <input type="text" placeholder="Full name" className="w-full px-8 py-5 rounded-2xl bg-slate-50 border border-zinc-200/50 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500/50 transition-all text-zinc-950 placeholder:text-zinc-400" />
                  </div>
                  <div className="text-left">
                    <label className="block text-xs uppercase tracking-widest font-black text-zinc-500 mb-4 ml-2">Email</label>
                    <input type="email" placeholder="example@email.com" className="w-full px-8 py-5 rounded-2xl bg-slate-50 border border-zinc-200/50 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500/50 transition-all text-zinc-950 placeholder:text-zinc-400" />
                  </div>
                </div>
                <div className="text-left">
                  <label className="block text-xs uppercase tracking-widest font-black text-zinc-500 mb-4 ml-2">Message</label>
                  <textarea placeholder="Write your message..." rows={5} className="w-full px-8 py-5 rounded-2xl bg-slate-50 border border-zinc-200/50 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500/50 transition-all text-zinc-950 placeholder:text-zinc-400" />
                </div>
                <button className="w-full py-6 bg-blue-600 text-white rounded-full font-black text-xl hover:bg-blue-700 transition-all shadow-2xl shadow-blue-500/20 active:scale-[0.98]">
                  Send Message
                </button>
              </div>
            </div>
            
            {/* Background Gradients for the form card */}
            <div className="absolute bottom-0 right-0 w-[500px] h-[500px] bg-blue-500/5 blur-[150px] rounded-full translate-x-1/2 translate-y-1/2" />
            <div className="absolute top-0 left-0 w-[400px] h-[400px] bg-zinc-950/5 blur-[120px] rounded-full -translate-x-1/2 -translate-y-1/2" />
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-20 px-6 border-t border-zinc-100 bg-slate-50/30">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-12">
          <div className="text-center md:text-left space-y-4">
            <div className="flex items-center gap-2 justify-center md:justify-start">
              <Image 
                src="/nimmi-logo-new.png" 
                alt="Nimmi AI Logo" 
                width={250} 
                height={80} 
                className="h-20 w-auto object-contain scale-[2] origin-left"
              />
            </div>
            <p className="text-zinc-500 text-sm max-w-xs leading-relaxed font-semibold">
              Ready to launch your vision? Our passionate team is here to take your idea and make it real.
            </p>
            <div className="flex items-center gap-4 justify-center md:justify-start pt-4">
               {[1, 2, 3, 4].map(i => (
                 <div key={i} className="w-10 h-10 rounded-full border border-zinc-200 flex items-center justify-center text-zinc-400 hover:text-zinc-950 hover:border-zinc-400 transition-all cursor-pointer bg-white">
                   <div className="w-1.5 h-1.5 bg-current rounded-full" />
                 </div>
               ))}
            </div>
          </div>
          
          <p className="text-zinc-400 text-sm font-black tracking-widest uppercase">© 2026 Nimmi AI. ALL RIGHTS RESERVED.</p>
        </div>
      </footer>
    </div>
  );
}
