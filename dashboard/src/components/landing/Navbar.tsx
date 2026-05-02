"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import { Menu, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

const navLinks = ["Home", "About", "How it Works", "Services", "Blog"];

export default function Navbar() {
  const [mobileMenu, setMobileMenu] = useState(false);

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-white/90 backdrop-blur-xl border-b border-zinc-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        <Link href="/" className="relative h-10 sm:h-14 w-28 sm:w-36 flex items-center">
          <Image 
            src="/nimmi-logo-new.png" 
            alt="Nimmi AI" 
            fill 
            className="object-contain object-left scale-[2.5] sm:scale-[3.2] origin-left" 
            priority 
          />
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
          <motion.div 
            initial={{ opacity: 0, height: 0 }} 
            animate={{ opacity: 1, height: "auto" }} 
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden bg-white/95 backdrop-blur-xl border-t border-zinc-100 overflow-hidden shadow-2xl"
          >
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
  );
}
