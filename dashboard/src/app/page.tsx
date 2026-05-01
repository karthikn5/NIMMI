"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { ArrowRight, MessageSquare, Check, Sparkles, Zap, Globe, Menu, X, ChevronRight, Play, Bot, Paintbrush, MousePointerClick, ShoppingCart, Code2, Settings2, Brain, Rocket, ChevronUp } from "lucide-react";
import { motion, AnimatePresence, useScroll, useSpring, useInView, useMotionValue, useTransform, Variants } from "framer-motion";
import Image from "next/image";

const navLinks = ["Home", "About", "How it Works", "Services"];

const features = [
  { icon: Brain, title: "Natural Conversations", desc: "AI that understands context, tone, and intent — not just keywords." },
  { icon: Sparkles, title: "Beautiful Interfaces", desc: "Customizable chat widgets that match your brand perfectly." },
  { icon: Zap, title: "Lightning Setup", desc: "Go from idea to live chatbot in under 10 minutes." },
];

const stats = [
  { value: "99%", label: "CLIENT SATISFACTION" },
  { value: "50+", label: "AI PROJECTS LIVE" },
  { value: "10M+", label: "MESSAGES HANDLED" },
  { value: "<2min", label: "AVG. SETUP TIME" },
];

const steps = [
  { num: "01", icon: MessageSquare, title: "Design Your Bot", desc: "Choose a template or start from scratch. Define your bot's personality, tone, and conversation flows with our visual builder." },
  { num: "02", icon: Brain, title: "Train & Customize", desc: "Upload your knowledge base, FAQs, or documents. Fine-tune responses until your bot sounds exactly like your brand.", highlight: true },
  { num: "03", icon: Rocket, title: "Deploy Anywhere", desc: "Embed on your website, connect to WhatsApp, Slack, or any platform. Go live with one click." },
];

const services = [
  { icon: Bot, title: "AI Integration", desc: "Custom LLM-powered solutions tailored to your business needs and workflows." },
  { icon: Code2, title: "Premium UI/UX", desc: "Design-first approach creating high-fidelity, interactive chat experiences." },
  { icon: Globe, title: "Custom Development", desc: "Full-stack development of robust, scalable chatbot applications." },
  { icon: ShoppingCart, title: "E-commerce Bots", desc: "Specialized shopping assistants that drive conversions and delight customers." },
  { icon: MousePointerClick, title: "Multi-Platform", desc: "Deploy across web, mobile, WhatsApp, Telegram, and more seamlessly." },
  { icon: Settings2, title: "Custom Solutions", desc: "Bespoke integrations and architectures tailored to your unique vision." },
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

export default function LandingPage() {
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

  if (!mounted) return null;

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
              <a key={item} href={`#${item.toLowerCase().replace(/\s+/g, '-')}`}
                className="text-sm font-medium text-zinc-500 hover:text-zinc-900 transition-colors">
                {item}
              </a>
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
              className="md:hidden bg-white border-t border-zinc-100 overflow-hidden">
              <div className="p-6 flex flex-col gap-4">
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
          <motion.div initial={{ opacity: 0, y: 50 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}>
            <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-purple-50 border border-purple-100 rounded-full mb-8">
              <Sparkles size={14} className="text-[#9d55ac]" />
              <span className="text-sm font-medium text-[#9d55ac]">Your AI chatbot, your way</span>
            </div>

            <h1 className="text-3xl sm:text-5xl md:text-6xl lg:text-7xl font-bold leading-[1.1] mb-4 sm:mb-6">
              Build chatbots<br />
              <span className="text-[#9d55ac]">that feel human.</span>
            </h1>

            <div className="w-16 h-0.5 bg-zinc-300 mb-6" />

            <p className="text-zinc-500 text-base sm:text-lg leading-relaxed mb-6 sm:mb-8 max-w-lg">
              Design, train, and deploy beautiful AI chatbots without writing a single line of code. Make every conversation meaningful.
            </p>

            <div className="flex flex-col sm:flex-row flex-wrap gap-3 sm:gap-4 mb-6">
              <Link href="/auth/signup"
                className="inline-flex items-center justify-center gap-2 px-5 sm:px-7 py-3 bg-[#9d55ac] text-white rounded-lg font-semibold hover:bg-[#8a4a97] transition-all shadow-lg shadow-[#9d55ac]/25 text-sm sm:text-base">
                Start Building Free <ArrowRight size={18} />
              </Link>
              <button className="inline-flex items-center justify-center gap-2 px-5 sm:px-7 py-3 bg-white border border-zinc-200 rounded-lg font-semibold text-zinc-700 hover:bg-zinc-50 transition-all shadow-sm text-sm sm:text-base">
                <Play size={16} /> Watch Demo
              </button>
            </div>

            <div className="flex items-center gap-6 text-sm text-zinc-500">
              <span className="flex items-center gap-1.5"><Check size={16} className="text-[#9d55ac]" /> No credit card</span>
              <span className="flex items-center gap-1.5"><Check size={16} className="text-[#9d55ac]" /> Free forever plan</span>
            </div>
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

            <div className="relative w-[240px] h-[240px] sm:w-[320px] sm:h-[320px] md:w-[420px] md:h-[420px]">
              <Image src="/robot-mascot.png" alt="AI Chatbot Mascot" fill className="object-contain drop-shadow-2xl" priority />
            </div>
          </motion.div>
        </div>
      </section>

      {/* ─── WHY CHOOSE NIMMI AI ─── */}
      <section id="about" className="py-16 sm:py-24 px-4 sm:px-6 bg-white">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-10 md:gap-16 items-start">
          <motion.div variants={sectionFade} initial="hidden" whileInView="visible" viewport={{ once: true }}>
            <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold leading-tight mb-4">
              Why teams choose<br /><span className="text-[#9d55ac]">Nimmi AI</span>
            </h2>
            <p className="text-zinc-500 leading-relaxed mb-10 max-w-md">
              We don&apos;t just build chatbots. We craft intelligent, empathetic conversational experiences that your customers genuinely enjoy using.
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
                    className="w-10 h-10 rounded-xl bg-purple-100 flex items-center justify-center shrink-0">
                    <f.icon size={20} className="text-[#9d55ac]" />
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
          <motion.div initial={{ opacity: 0, y: 40, scale: 0.95 }} whileInView={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }} viewport={{ once: true }}
            className="bg-white rounded-3xl shadow-xl border border-zinc-100 overflow-hidden">
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
        <motion.div className="max-w-7xl mx-auto mt-12 sm:mt-20 grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4"
          variants={staggerContainer} initial="hidden" whileInView="visible" viewport={{ once: true }}>
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
          <motion.div variants={sectionFade} initial="hidden" whileInView="visible" viewport={{ once: true }} className="text-center mb-16">
            <span className="inline-block px-4 py-1.5 bg-purple-50 border border-purple-100 rounded-full text-sm font-medium text-[#9d55ac] mb-4">
              Simple Process
            </span>
            <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold mb-4">How it works</h2>
            <p className="text-zinc-500 max-w-xl mx-auto">Three simple steps to your perfect AI chatbot. No coding, no complexity.</p>
          </motion.div>

          <motion.div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6 relative"
            variants={staggerContainer} initial="hidden" whileInView="visible" viewport={{ once: true }}>
            {/* Dashed connector line */}
            <motion.div initial={{ scaleX: 0 }} whileInView={{ scaleX: 1 }} transition={{ duration: 1, delay: 0.5 }} viewport={{ once: true }}
              className="hidden md:block absolute top-1/2 left-[33%] right-[33%] h-px border-t-2 border-dashed border-zinc-200 -translate-y-1/2 z-0 origin-left" />

            {steps.map((s, i) => (
              <motion.div key={i} variants={staggerItem}
                whileHover={{ y: -8, transition: { duration: 0.3 } }}
                className={`relative z-10 p-6 sm:p-8 rounded-3xl border transition-all hover:shadow-lg ${
                  s.highlight ? "bg-purple-50 border-purple-200 shadow-md" : "bg-white border-zinc-100 hover:border-purple-100"
                }`}>
                <motion.div initial={{ opacity: 0, scale: 0.5 }} whileInView={{ opacity: 1, scale: 1 }} transition={{ delay: 0.3 + i * 0.15, type: "spring" }} viewport={{ once: true }}
                  className="absolute top-6 right-8 text-6xl font-bold text-zinc-100 select-none">{s.num}</motion.div>
                <motion.div whileInView={{ rotate: [0, -15, 15, 0] }} transition={{ duration: 0.5, delay: i * 0.2 }} viewport={{ once: true }}
                  className="w-12 h-12 rounded-2xl bg-purple-100 flex items-center justify-center mb-6">
                  <s.icon size={22} className="text-[#9d55ac]" />
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

            <span className="inline-block px-4 py-1.5 bg-purple-50 border border-purple-100 rounded-full text-sm font-medium text-[#9d55ac] mb-4">
              What We Offer
            </span>
            <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold mb-4">Our Services</h2>
            <p className="text-zinc-500 max-w-xl mx-auto">Everything you need to build, launch, and scale your conversational AI.</p>
          </motion.div>

          <motion.div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 sm:gap-6"
            variants={staggerContainer} initial="hidden" whileInView="visible" viewport={{ once: true }}>
            {services.map((s, i) => (
              <motion.div key={i} variants={staggerItem}
                whileHover={{ y: -8, scale: 1.02, transition: { duration: 0.3 } }}
                className="p-6 sm:p-8 bg-[#faf9f7] rounded-3xl border border-zinc-100 hover:border-purple-200 hover:shadow-lg transition-all group cursor-default">
                <motion.div whileInView={{ scale: [0.5, 1.15, 1] }} transition={{ duration: 0.5, delay: i * 0.08 }} viewport={{ once: true }}
                  className="w-12 h-12 rounded-2xl bg-purple-100 flex items-center justify-center mb-6 group-hover:bg-purple-200 transition-colors">
                  <s.icon size={22} className="text-[#9d55ac]" />
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
      <footer className="py-10 sm:py-16 px-4 sm:px-6 border-t border-zinc-100 bg-white">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6 sm:gap-8">
          <div className="relative h-16 sm:h-20 w-48 sm:w-64">
            <Image src="/nimmi-logo-new.png" alt="Nimmi AI" fill className="object-contain object-center md:object-left" />
          </div>

          <div className="flex flex-wrap items-center justify-center gap-4 sm:gap-8">
            {navLinks.map((item) => (
              <a key={item} href={`#${item.toLowerCase().replace(/\s+/g, '-')}`}
                className="text-sm text-zinc-500 hover:text-zinc-900 transition-colors">{item}</a>
            ))}
          </div>

          <p className="text-sm text-zinc-400">© 2026 Nimmi AI. All rights reserved.</p>
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
