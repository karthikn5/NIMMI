"use client";

import { useState, useEffect, useRef } from "react";
import { useInView } from "framer-motion";
import Image from "next/image";

const stats = [
  { value: "99%", label: "CLIENT SATISFACTION" },
  { value: "50+", label: "AI PROJECTS LIVE" },
  { value: "10M+", label: "MESSAGES HANDLED" },
  { value: "<2min", label: "AVG. SETUP TIME" },
];

function AnimatedCounter({ value, duration = 2 }: { value: string; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-50px" });
  const [displayValue, setDisplayValue] = useState("0");

  useEffect(() => {
    if (!isInView) return;
    const match = value.match(/^([<>]?)([\d.]+)(\+?)(.*?)$/);
    if (!match) { setDisplayValue(value); return; }
    const [, prefix, numStr, plus, suffix] = match;
    const target = parseFloat(numStr);
    const isDecimal = numStr.includes('.');
    const startTime = Date.now();
    const animate = () => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / (duration * 1000), 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = eased * target;
      setDisplayValue(`${prefix}${isDecimal ? current.toFixed(1) : Math.round(current)}${plus}${suffix}`);
      if (progress < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }, [isInView, value, duration]);

  return <span ref={ref}>{isInView ? displayValue : "0"}</span>;
}

export default function Stats() {
  return (
    <div className="max-w-7xl mx-auto mt-12 sm:mt-20 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 sm:gap-4 relative px-4 sm:px-6">
      {stats.map((s, i) => (
        <div key={i}
          className="text-center py-6 sm:py-8 px-3 sm:px-4 bg-[#faf9f7] rounded-2xl border border-zinc-100 hover:border-purple-200 transition-colors cursor-default">
          <p className="text-2xl sm:text-3xl md:text-4xl font-bold text-zinc-900">
            <AnimatedCounter value={s.value} duration={2} />
          </p>
          <p className="text-[10px] sm:text-xs font-semibold uppercase tracking-wider text-zinc-400 mt-1 sm:mt-2">{s.label}</p>
        </div>
      ))}
    </div>
  );
}
