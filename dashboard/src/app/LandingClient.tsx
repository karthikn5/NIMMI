"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { ArrowRight, MessageSquare, Check, Sparkles, Zap, Globe, Menu, X, ChevronRight, Play, Bot, Paintbrush, MousePointerClick, ShoppingCart, Code2, Settings2, Brain, Rocket, ChevronUp, Twitter, Linkedin } from "lucide-react";
import { motion, AnimatePresence, useScroll, useSpring, useInView, useMotionValue, useTransform, Variants } from "framer-motion";
import Image from "next/image";

const navLinks = ["Home", "About", "How it Works", "Services", "Blog"];

const features = [
  { image: "/feat-brain.png", title: "Natural Conversations", desc: "AI that understands context, tone, and intent — not just keywords." },
  { image: "/feat-design.png", title: "Beautiful Interfaces", desc: "Customizable chat widgets that match your brand perfectly." },
  { image: "/feat-rocket.png", title: "Lightning Setup", desc: "Go from idea to live chatbot in under 10 minutes." },
];

const stats = [
  { value: "99%", label: "CLIENT SATISFACTION" },
  { value: "50+", label: "AI PROJECTS LIVE" },
  { value: "10M+", label: "MESSAGES HANDLED" },
  { value: "<2min", label: "AVG. SETUP TIME" },
];

const steps = [
  { num: "01", image: "/step-pencil.png", title: "Design Your Bot", desc: "Choose a template or start from scratch. Define your bot's personality, tone, and conversation flows with our visual builder." },
  { num: "02", image: "/feat-brain.png", title: "Train & Customize", desc: "Upload your knowledge base, FAQs, or documents. Fine-tune responses until your bot sounds exactly like your brand.", highlight: true },
  { num: "03", image: "/feat-rocket.png", title: "Deploy Anywhere", desc: "Embed on your website, connect to WhatsApp, Slack, or any platform. Go live with one click." },
];

const services = [
  { image: "/service-ai.png", title: "AI Integration", desc: "Custom LLM-powered solutions tailored to your business needs and workflows." },
  { image: "/service-uiux.png", title: "Premium UI/UX", desc: "Design-first approach creating high-fidelity, interactive chat experiences." },
  { image: "/service-dev.png", title: "Custom Development", desc: "Full-stack development of robust, scalable chatbot applications." },
  { image: "/service-cart.png", title: "E-commerce Bots", desc: "Specialized shopping assistants that drive conversions and delight customers." },
  { image: "/chat-3d.png", title: "Multi-Platform", desc: "Deploy across web, mobile, WhatsApp, Telegram, and more seamlessly." },
  { image: "/gear-3d.png", title: "Custom Solutions", desc: "Bespoke integrations and architectures tailored to your unique vision." },
];

const sectionFade: Variants = {
  hidden: { opacity: 0, y: 40 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: "easeOut" } },
};

// Animated counter component for stats
function AnimatedCounter({ value, duration = 2 }: { value: string; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-50px" });
  const [displayValue, setDisplayValue] = useState("0");

  useEffect(() => {
    if (!isInView) return;
    // Extract numeric part and suffix
    const match = value.match(/^([<>]?)([\d.]+)(\+?)(.*?)$/);
    if (!match) { setDisplayValue(value); return; }
    const [, prefix, numStr, plus, suffix] = match;
    const target = parseFloat(numStr);
    const isDecimal = numStr.includes('.');
    const startTime = Date.now();
    const animate = () => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / (duration * 1000), 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = eased * target;
      setDisplayValue(`${prefix}${isDecimal ? current.toFixed(1) : Math.round(current)}${plus}${suffix}`);
      if (progress < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }, [isInView, value, duration]);

  return <span ref={ref}>{isInView ? displayValue : "0"}</span>;
}

// Stagger container variants
const staggerContainer: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.12, delayChildren: 0.1 } },
};

const staggerItem: Variants = {
  hidden: { opacity: 0, y: 30, scale: 0.95 },
  visible: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.5, ease: "easeOut" } },
};

export default function LandingClient() {
  const [mounted, setMounted] = useState(false);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 100, damping: 30 });

  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    const handleScroll = () => setShowScrollTop(window.scrollY > 400);
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  // Removed return null for SEO: Ensures crawlers see content before hydration.

  const scrollToTop = () => window.scrollTo({ top: 0, behavior: "smooth" });

  return (
    <div className="min-h-screen bg-[#faf9f7] text-zinc-900 font-[family-name:var(--font-geist-sans)] overflow-x-hidden">
      {/* ─── SCROLL PROGRESS BAR ─── */}
      <motion.div style={{ scaleX }} className="fixed top-0 left-0 right-0 h-1 bg-[#9d55ac] origin-left z-[60]" />

      {/* ─── NAVIGATION ─── */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white/90 backdrop-blur-xl border-b border-zinc-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <Link href="/" className="relative h-10 sm:h-14 w-28 sm:w-36 flex items-center">
            <Image src="/nimmi-logo-new.png" alt="Nimmi AI" fill className="object-contain object-left scale-[2.5] sm:scale-[3.2] origin-left" priority />
          </Link>

          <div className="hidden md:flex items-center gap-8">
            {navLinks.map((item) => (
              <Link key={item} 
                href={item === "Blog" ? "/blog" : `#${item.toLowerCase().replace(/\s+/g, '-')}`}
                className="text-sm font-medium text-zinc-500 hover:text-[#9d55ac] transition-colors"
              >
                {item}
              </Link>
            ))}
          </div>

          <div className="hidden md:flex items-center gap-4">
            <Link href="/auth/login" className="text-sm font-semibold text-zinc-700 hover:text-zinc-900 transition-colors">Sign In</Link>
            <Link href="/auth/signup" className="px-5 py-2 bg-[#9d55ac] text-white rounded-lg text-sm font-semibold hover:bg-[#8a4a97] transition-all shadow-md shadow-purple-500/20">
              Get Started
            </Link>
          </div>

          <button onClick={() => setMobileMenu(!mobileMenu)} className="md:hidden p-2 text-zinc-700" aria-label="Toggle Menu">
            {mobileMenu ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>

        <AnimatePresence>
          {mobileMenu && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
              className="md:hidden bg-white/95 backdrop-blur-xl border-t border-zinc-100 overflow-hidden shadow-2xl">
              <div className="p-6 flex flex-col gap-5">
                {navLinks.map((item) => (
                  <a key={item} href={`#${item.toLowerCase().replace(/\s+/g, '-')}`}
                    onClick={() => setMobileMenu(false)}
                    className="text-lg font-semibold text-zinc-800 py-2">{item}</a>
                ))}
                <div className="flex gap-3 mt-4 pt-4 border-t border-zinc-100">
                  <Link href="/auth/login" onClick={() => setMobileMenu(false)}
                    className="flex-1 py-3 text-center text-sm font-semibold border border-zinc-200 rounded-lg">Sign In</Link>
                  <Link href="/auth/signup" onClick={() => setMobileMenu(false)}
                    className="flex-1 py-3 text-center text-sm font-semibold text-white bg-[#9d55ac] rounded-lg">Get Started</Link>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </nav>

      {/* ─── HERO SECTION ─── */}
      <section id="home" className="pt-24 sm:pt-32 pb-12 sm:pb-20 px-4 sm:px-6">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-8 md:gap-12 items-center">
          <motion.div initial="hidden" animate="visible" variants={staggerContainer} className="text-center md:text-left z-10">
            <motion.div variants={staggerItem} className="inline-flex items-center gap-2 px-4 py-1.5 bg-purple-50 border border-purple-100 rounded-full mb-8 mx-auto md:mx-0">
              <Sparkles size={14} className="text-[#9d55ac]" />
              <span className="text-sm font-medium text-[#9d55ac]">Your AI chatbot, your way</span>
            </motion.div>

            <motion.h1 variants={staggerItem} className="text-3xl sm:text-5xl md:text-6xl lg:text-7xl font-bold leading-[1.1] mb-4 sm:mb-6">
              Build Your Own Custom <br />
              <span className="text-[#9d55ac]">AI Chatbot — No Code Needed.</span>
            </motion.h1>

            <motion.div variants={staggerItem} className="w-16 h-0.5 bg-zinc-300 mb-6 mx-auto md:mx-0" />

            <motion.p variants={staggerItem} className="text-zinc-500 text-base sm:text-lg leading-relaxed mb-6 sm:mb-8 max-w-lg mx-auto md:mx-0">
              Design, train, and deploy a <strong>custom AI chatbot for your website</strong> in India without writing a single line of code. Nimmi AI is the most powerful <strong>chatbot builder India</strong> has to offer for modern businesses.
            </motion.p>

            <motion.div variants={staggerItem} className="flex flex-col sm:flex-row flex-wrap gap-3 sm:gap-4 mb-8 items-stretch sm:items-center">
              <Link href="/auth/signup"
                className="inline-flex items-center justify-center gap-2 px-5 sm:px-7 py-3 bg-[#9d55ac] text-white rounded-lg font-semibold hover:bg-[#8a4a97] transition-all shadow-lg shadow-[#9d55ac]/25 text-sm sm:text-base">
                Start Building Free <ArrowRight size={18} />
              </Link>
              <button className="inline-flex items-center justify-center gap-2 px-5 sm:px-7 py-3 bg-white border border-zinc-200 rounded-lg font-semibold text-zinc-700 hover:bg-zinc-50 transition-all shadow-sm text-sm sm:text-base">
                <Play size={16} /> Watch Demo
              </button>
            </motion.div>

            <motion.div variants={staggerItem} className="flex flex-wrap items-center justify-center md:justify-start gap-4 sm:gap-6 text-sm text-zinc-500">
              <span className="flex items-center gap-1.5"><Check size={16} className="text-[#9d55ac]" /> No credit card</span>
              <span className="flex items-center gap-1.5"><Check size={16} className="text-[#9d55ac]" /> Free forever plan</span>
            </motion.div>
          </motion.div>

          <motion.div initial={{ opacity: 0, scale: 0.85, rotate: -2 }} animate={{ opacity: 1, scale: 1, rotate: 0 }} transition={{ duration: 0.8, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="relative flex items-center justify-center">
            {/* Floating badges */}
            <motion.div animate={{ y: [0, -8, 0] }} transition={{ duration: 3, repeat: Infinity }}
              className="absolute top-4 right-4 md:right-8 z-20 flex items-center gap-2 px-4 py-2 bg-white rounded-full shadow-lg border border-zinc-100">
              <Bot size={16} className="text-[#9d55ac]" />
              <span className="text-xs font-semibold text-zinc-700">AI Powered</span>
            </motion.div>

            <motion.div animate={{ y: [0, 6, 0] }} transition={{ duration: 3.5, repeat: Infinity }}
              className="absolute bottom-12 left-4 md:left-8 z-20 flex items-center gap-2 px-4 py-2 bg-white rounded-full shadow-lg border border-zinc-100">
              <span className="text-[#9d55ac] font-bold text-sm">+</span>
              <span className="text-xs font-semibold text-zinc-700">Instant Setup</span>
            </motion.div>

            {/* Decorative dots */}
            <div className="absolute top-1/4 left-0 w-2 h-2 rounded-full bg-purple-300 opacity-60" />
            <div className="absolute bottom-1/3 right-0 w-3 h-3 rounded-full bg-purple-200 opacity-50" />
            <div className="absolute top-10 left-1/4 w-1.5 h-1.5 rounded-full bg-orange-300 opacity-60" />

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
          </motion.div>
        </div>
      </section>

      {/* ─── WHY CHOOSE NIMMI AI ─── */}
      <section id="about" className="py-16 sm:py-24 px-4 sm:px-6 bg-white">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-10 md:gap-16 items-start">
          <motion.div variants={sectionFade} initial="hidden" whileInView="visible" viewport={{ once: true }}>
            <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold leading-tight mb-4">
              Why Business Teams Choose<br /><span className="text-[#9d55ac]">Nimmi AI</span>
            </h2>
            <p className="text-zinc-500 leading-relaxed mb-10 max-w-md">
              We don&apos;t just build bots. We craft intelligent, empathetic conversational experiences. Nimmi AI is the leading <strong>custom AI chatbot India</strong>-based platform for creating high-conversion assistants.
            </p>

            <motion.div className="space-y-4" variants={staggerContainer} initial="hidden" whileInView="visible" viewport={{ once: true }}>
              {features.map((f, i) => (
                <motion.div key={i} variants={staggerItem}
                  whileHover={{ x: 8, transition: { duration: 0.2 } }}
                  className="flex items-start gap-4 p-5 bg-[#faf9f7] rounded-2xl border border-zinc-100 hover:border-purple-200 hover:shadow-md transition-all cursor-default">
                  <motion.div
                    whileInView={{ rotate: [0, -10, 10, 0] }}
                    transition={{ duration: 0.6, delay: i * 0.15 }}
                    viewport={{ once: true }}
                    className="w-12 h-12 rounded-xl bg-purple-100 flex items-center justify-center shrink-0 relative overflow-hidden">
                    <Image 
                      src={f.image} 
                      alt={f.title} 
                      fill 
                      sizes="48px"
                      className="object-contain p-1.5 mix-blend-multiply" 
                      loading="lazy"
                    />
                  </motion.div>
                  <div>
                    <h3 className="font-semibold text-zinc-900 mb-1">{f.title}</h3>
                    <p className="text-sm text-zinc-500 leading-relaxed">{f.desc}</p>
                  </div>
                </motion.div>
              ))}
            </motion.div>
          </motion.div>

          {/* Chat Mockup */}
          <motion.div initial={{ opacity: 0, x: 50 }} whileInView={{ opacity: 1, x: 0 }} transition={{ duration: 0.8 }} viewport={{ once: true }}
            className="relative scale-90 sm:scale-100 origin-top bg-white rounded-3xl shadow-xl border border-zinc-100 overflow-hidden">
            <div className="flex items-center gap-2 px-5 py-3 border-b border-zinc-100">
              <div className="w-3 h-3 rounded-full bg-red-400" />
              <div className="w-3 h-3 rounded-full bg-yellow-400" />
              <div className="w-3 h-3 rounded-full bg-green-400" />
            </div>
            <div className="p-6 space-y-4">
              {/* Bot message */}
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-full bg-purple-100 shrink-0" />
                <div className="bg-zinc-100 rounded-2xl rounded-tl-md px-4 py-3 max-w-[80%]">
                  <p className="text-sm text-zinc-700">Hi! How can I help you today? 😊</p>
                </div>
              </div>
              {/* User message */}
              <div className="flex justify-end">
                <div className="bg-[#9d55ac] rounded-2xl rounded-tr-md px-4 py-3 max-w-[80%]">
                  <p className="text-sm text-white">I want to set up a chatbot for my store</p>
                </div>
              </div>
              {/* Bot response */}
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-full bg-purple-100 shrink-0" />
                <div className="bg-zinc-100 rounded-2xl rounded-tl-md px-4 py-3 max-w-[80%]">
                  <p className="text-sm text-zinc-700">Great choice! I can help with that. Let me walk you through — it only takes a few minutes ✨</p>
                </div>
              </div>
              {/* Typing indicator */}
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-full bg-purple-100 shrink-0" />
                <div className="flex gap-1 items-center px-4 py-3">
                  <div className="w-2 h-2 rounded-full bg-zinc-300 animate-bounce" style={{ animationDelay: "0ms" }} />
                  <div className="w-2 h-2 rounded-full bg-zinc-300 animate-bounce" style={{ animationDelay: "150ms" }} />
                  <div className="w-2 h-2 rounded-full bg-zinc-300 animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              </div>
            </div>
          </motion.div>
        </div>

        {/* Stats Bar */}
        <motion.div className="max-w-7xl mx-auto mt-12 sm:mt-20 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 sm:gap-4 relative"
          variants={staggerContainer} initial="hidden" whileInView="visible" viewport={{ once: true }}>
          {/* Decorative icons for stats */}
          <motion.div animate={{ scale: [1, 1.15, 1], rotate: [0, 10, 0] }} transition={{ duration: 4, repeat: Infinity }}
            className="absolute -left-6 -top-6 w-10 h-10 hidden lg:block opacity-60">
            <Image src="/heart-3d.png" alt="Heart" fill className="object-contain mix-blend-multiply" />
          </motion.div>
          <motion.div animate={{ y: [0, -10, 0], rotate: [0, -10, 0] }} transition={{ duration: 3.5, repeat: Infinity }}
            className="absolute -right-6 -bottom-6 w-12 h-12 hidden lg:block opacity-50">
            <Image src="/bolt-3d.png" alt="Bolt" fill className="object-contain mix-blend-multiply" />
          </motion.div>
          {stats.map((s, i) => (
            <motion.div key={i} variants={staggerItem}
              whileHover={{ y: -6, boxShadow: "0 20px 40px -12px rgba(157,85,172,0.15)", transition: { duration: 0.3 } }}
              className="text-center py-6 sm:py-8 px-3 sm:px-4 bg-[#faf9f7] rounded-2xl border border-zinc-100 hover:border-purple-200 transition-colors cursor-default">
              <p className="text-2xl sm:text-3xl md:text-4xl font-bold text-zinc-900">
                <AnimatedCounter value={s.value} duration={2} />
              </p>
              <motion.p initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} transition={{ delay: 0.8 + i * 0.1 }} viewport={{ once: true }}
                className="text-[10px] sm:text-xs font-semibold uppercase tracking-wider text-zinc-400 mt-1 sm:mt-2">{s.label}</motion.p>
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* ─── HOW IT WORKS ─── */}
      <section id="how-it-works" className="py-16 sm:py-24 px-4 sm:px-6 bg-[#faf9f7]">
        <div className="max-w-7xl mx-auto">
          <motion.div variants={sectionFade} initial="hidden" whileInView="visible" viewport={{ once: true }} className="text-center mb-16 relative">
            {/* Floating Decorative Icons */}
            <motion.div animate={{ rotate: [0, 10, -10, 0], scale: [1, 1.1, 1] }} transition={{ duration: 4, repeat: Infinity }}
              className="absolute -top-10 -left-4 w-12 h-12 hidden md:block opacity-60">
              <Image src="/spark-3d.png" alt="Spark" fill className="object-contain mix-blend-multiply" />
            </motion.div>
            <motion.div animate={{ y: [0, 12, 0], rotate: [0, -5, 5, 0] }} transition={{ duration: 5, repeat: Infinity }}
              className="absolute top-20 -right-8 w-16 h-16 hidden md:block opacity-40">
              <Image src="/chat-3d.png" alt="Chat" fill className="object-contain mix-blend-multiply" />
            </motion.div>

            <span className="inline-block px-4 py-1.5 bg-purple-50 border border-purple-100 rounded-full text-sm font-medium text-[#9d55ac] mb-4">
              Simple Process
            </span>
            <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold mb-4">How to Build Your AI Chatbot</h2>
            <p className="text-zinc-500 max-w-xl mx-auto">Three simple steps to create your perfect AI chatbot in India. No coding, no complexity.</p>
          </motion.div>

          <motion.div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6 relative"
            variants={staggerContainer} initial="hidden" whileInView="visible" viewport={{ once: true }}>
            {/* Dashed connector line */}
            <motion.div initial={{ scaleX: 0 }} whileInView={{ scaleX: 1 }} transition={{ duration: 1, delay: 0.5 }} viewport={{ once: true }}
              className="hidden md:block absolute top-1/2 left-[33%] right-[33%] h-px border-t-2 border-dashed border-zinc-200 -translate-y-1/2 z-0 origin-left" />

            {steps.map((s, i) => (
              <motion.div key={i} variants={staggerItem}
                whileHover={{ y: -8, transition: { duration: 0.3 } }}
                className={`relative z-10 p-6 sm:p-8 rounded-3xl border transition-all hover:shadow-lg ${s.highlight ? "bg-purple-50 border-purple-200 shadow-md" : "bg-white border-zinc-100 hover:border-purple-100"
                  }`}>
                <motion.div initial={{ opacity: 0, scale: 0.5 }} whileInView={{ opacity: 1, scale: 1 }} transition={{ delay: 0.3 + i * 0.15, type: "spring" }} viewport={{ once: true }}
                  className="absolute top-6 right-8 text-6xl font-bold text-zinc-100 select-none">{s.num}</motion.div>
                <motion.div whileInView={{ rotate: [0, -15, 15, 0] }} transition={{ duration: 0.5, delay: i * 0.2 }} viewport={{ once: true }}
                  className="w-16 h-16 rounded-2xl bg-purple-100 flex items-center justify-center mb-6 relative overflow-hidden">
                  <Image 
                    src={s.image} 
                    alt={s.title} 
                    fill 
                    sizes="64px"
                    className="object-contain p-2 mix-blend-multiply" 
                    loading="lazy"
                  />
                </motion.div>
                <h3 className="text-xl font-bold mb-3">{s.title}</h3>
                <p className="text-sm text-zinc-500 leading-relaxed">{s.desc}</p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ─── OUR SERVICES ─── */}
      <section id="services" className="py-16 sm:py-24 px-4 sm:px-6 bg-white relative overflow-hidden">
        <div className="max-w-7xl mx-auto">
          <motion.div variants={sectionFade} initial="hidden" whileInView="visible" viewport={{ once: true }} className="text-center mb-10 sm:mb-16 relative">
            {/* Mascot next to heading */}
            <motion.div
              animate={{ y: [0, -8, 0] }}
              transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
              className="hidden sm:block absolute left-2 sm:left-[calc(50%-320px)] md:left-[calc(50%-350px)] top-1/2 -translate-y-1/2 w-[80px] h-[80px] sm:w-[120px] sm:h-[120px] md:w-[150px] md:h-[150px] z-10"
            >
              <Image src="/robot-mascot-2.png" alt="Nimmi AI Mascot" fill className="object-contain drop-shadow-lg" />
            </motion.div>

            {/* Floating Decorative Icons */}
            <motion.div animate={{ rotate: [0, 15, -15, 0], y: [0, -10, 0] }} transition={{ duration: 5, repeat: Infinity }}
              className="absolute right-0 sm:right-[15%] top-0 w-12 h-12 hidden sm:block opacity-60">
              <Image src="/spark-3d.png" alt="Spark" fill className="object-contain mix-blend-multiply" />
            </motion.div>
            <motion.div animate={{ rotate: [0, -20, 20, 0], y: [0, 10, 0] }} transition={{ duration: 6, repeat: Infinity }}
              className="absolute left-[20%] bottom-[-20px] w-14 h-14 hidden sm:block opacity-50">
              <Image src="/chat-3d.png" alt="Chat" fill className="object-contain mix-blend-multiply" />
            </motion.div>

            <span className="inline-block px-4 py-1.5 bg-purple-50 border border-purple-100 rounded-full text-sm font-medium text-[#9d55ac] mb-4">
              What We Offer
            </span>
            <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold mb-4">Our AI Chatbot Services</h2>
            <p className="text-zinc-500 max-w-xl mx-auto">Everything you need to build, launch, and scale your conversational AI business solutions.</p>
          </motion.div>

          <motion.div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6 sm:gap-6 relative"
            variants={staggerContainer} initial="hidden" whileInView="visible" viewport={{ once: true }}>
            {/* Background decorative gear */}
            <motion.div animate={{ rotate: 360 }} transition={{ duration: 15, repeat: Infinity, ease: "linear" }}
              className="absolute -right-12 bottom-1/4 w-20 h-20 hidden xl:block opacity-20 pointer-events-none">
              <Image src="/gear-3d.png" alt="Gear" fill className="object-contain mix-blend-multiply" />
            </motion.div>
            {services.map((s, i) => (
              <motion.div key={i} variants={staggerItem}
                whileHover={{ y: -8, scale: 1.02, transition: { duration: 0.3 } }}
                className="p-6 sm:p-8 bg-[#faf9f7] rounded-3xl border border-zinc-100 hover:border-purple-200 hover:shadow-lg transition-all group cursor-default">
                <motion.div whileInView={{ scale: [0.5, 1.15, 1] }} transition={{ duration: 0.5, delay: i * 0.08 }} viewport={{ once: true }}
                  className="w-16 h-16 rounded-2xl bg-purple-100 flex items-center justify-center mb-6 group-hover:bg-purple-200 transition-colors relative overflow-hidden">
                  <Image 
                    src={s.image} 
                    alt={s.title} 
                    fill 
                    sizes="64px"
                    className="object-contain p-2 mix-blend-multiply" 
                    loading="lazy"
                  />
                </motion.div>
                <h3 className="text-lg font-bold mb-2">{s.title}</h3>
                <p className="text-sm text-zinc-500 leading-relaxed">{s.desc}</p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ─── CTA BANNER ─── */}
      <section className="px-4 sm:px-6 pb-16 sm:pb-24">
        <motion.div initial={{ opacity: 0, y: 50, scale: 0.95 }} whileInView={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }} viewport={{ once: true }}
          className="max-w-5xl mx-auto relative overflow-hidden rounded-2xl sm:rounded-3xl bg-gradient-to-r from-[#6b2d7b] to-[#9d55ac] px-6 sm:px-8 md:px-16 py-10 sm:py-16 text-center">
          <div className="absolute top-6 left-8 w-2 h-2 rounded-full bg-white/30" />
          <div className="absolute top-10 left-16 w-1.5 h-1.5 rounded-full bg-white/20" />
          <div className="absolute bottom-8 right-12 w-3 h-3 rounded-full bg-white/10" />

          <h2 className="text-2xl sm:text-3xl md:text-4xl font-bold text-white mb-3 sm:mb-4">Ready to build your chatbot?</h2>
          <p className="text-purple-200 mb-6 sm:mb-8 max-w-md mx-auto text-sm sm:text-base">Join thousands of teams already using Nimmi AI to create smarter, more engaging conversations.</p>
          <div className="flex flex-col sm:flex-row flex-wrap justify-center gap-3 sm:gap-4">
            <Link href="/auth/signup"
              className="px-6 sm:px-8 py-3 bg-white text-[#9d55ac] rounded-lg font-semibold hover:bg-zinc-50 transition-all shadow-lg text-sm sm:text-base">
              Get Started Free
            </Link>
            <Link href="/auth/login"
              className="px-6 sm:px-8 py-3 border border-white/30 text-white rounded-lg font-semibold hover:bg-white/10 transition-all text-sm sm:text-base">
              Sign In
            </Link>
          </div>
        </motion.div>
      </section>

      {/* ─── FOOTER ─── */}
      <footer className="py-20 px-6 border-t border-zinc-100 bg-white">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-4 gap-12 sm:gap-16">
          <div className="col-span-1 md:col-span-1">
            <div className="relative h-12 w-32 mb-6">
              <Image src="/nimmi-logo-new.png" alt="Nimmi AI" fill className="object-contain object-left scale-[2.5]" />
            </div>
            <p className="text-zinc-500 text-sm leading-relaxed mb-6">
              Empowering businesses in India with smart, custom-trained AI chatbots.
            </p>
            <div className="flex gap-4">
               {/* Social placeholders */}
               <div className="w-8 h-8 rounded-full bg-zinc-50 flex items-center justify-center text-zinc-400 hover:text-[#9d55ac] transition-colors cursor-pointer"><Twitter size={16} /></div>
               <div className="w-8 h-8 rounded-full bg-zinc-50 flex items-center justify-center text-zinc-400 hover:text-[#9d55ac] transition-colors cursor-pointer"><Linkedin size={16} /></div>
            </div>
          </div>

          <div>
            <h4 className="font-bold text-zinc-900 mb-6 uppercase text-xs tracking-widest">Solutions</h4>
            <ul className="space-y-4">
              <li><Link href="/solutions/ecommerce" className="text-sm text-zinc-500 hover:text-[#9d55ac] transition-colors">E-commerce</Link></li>
              <li><Link href="/solutions/healthcare" className="text-sm text-zinc-500 hover:text-[#9d55ac] transition-colors">Healthcare</Link></li>
              <li><Link href="/solutions/real-estate" className="text-sm text-zinc-500 hover:text-[#9d55ac] transition-colors">Real Estate</Link></li>
              <li><Link href="/solutions/education" className="text-sm text-zinc-500 hover:text-[#9d55ac] transition-colors opacity-50 cursor-not-allowed">Education (Soon)</Link></li>
            </ul>
          </div>

          <div>
            <h4 className="font-bold text-zinc-900 mb-6 uppercase text-xs tracking-widest">Resources</h4>
            <ul className="space-y-4">
              <li><Link href="/blog" className="text-sm text-zinc-500 hover:text-[#9d55ac] transition-colors">Blog</Link></li>
              <li><Link href="/blog/how-to-build-custom-ai-chatbot-2026" className="text-sm text-zinc-500 hover:text-[#9d55ac] transition-colors">Tutorials</Link></li>
              <li><Link href="/blog/calculating-chatbot-roi" className="text-sm text-zinc-500 hover:text-[#9d55ac] transition-colors">ROI Calculator</Link></li>
              <li><Link href="/" className="text-sm text-zinc-500 hover:text-[#9d55ac] transition-colors">Documentation</Link></li>
            </ul>
          </div>

          <div>
            <h4 className="font-bold text-zinc-900 mb-6 uppercase text-xs tracking-widest">Company</h4>
            <ul className="space-y-4">
              <li><Link href="/" className="text-sm text-zinc-500 hover:text-[#9d55ac] transition-colors">About Us</Link></li>
              <li><Link href="/" className="text-sm text-zinc-500 hover:text-[#9d55ac] transition-colors">Contact</Link></li>
              <li><Link href="/" className="text-sm text-zinc-500 hover:text-[#9d55ac] transition-colors">Privacy Policy</Link></li>
              <li><Link href="/" className="text-sm text-zinc-500 hover:text-[#9d55ac] transition-colors">Terms of Service</Link></li>
            </ul>
          </div>
        </div>
        <div className="max-w-7xl mx-auto mt-20 pt-10 border-t border-zinc-50 flex flex-col md:row items-center justify-between gap-4">
           <p className="text-xs text-zinc-400">© 2026 Nimmi AI. Built for the future of Indian business.</p>
           <div className="flex gap-6 text-xs text-zinc-400 font-medium">
              <span>Made in India</span>
              <span className="w-1 h-1 rounded-full bg-zinc-200 mt-2" />
              <span>Version 2.4.0</span>
           </div>
        </div>
      </footer>

      {/* ─── SCROLL TO TOP BUTTON ─── */}
      <AnimatePresence>
        {showScrollTop && (
          <motion.button
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            onClick={scrollToTop}
            className="fixed bottom-4 right-4 sm:bottom-8 sm:right-8 z-50 w-10 h-10 sm:w-12 sm:h-12 bg-[#9d55ac] text-white rounded-full shadow-lg shadow-[#9d55ac]/30 flex items-center justify-center hover:bg-[#8a4a97] transition-colors"
            aria-label="Scroll to top"
          >
            <ChevronUp size={22} />
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
}
