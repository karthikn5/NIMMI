import Link from "next/link";
import Image from "next/image";
import { Twitter, Linkedin, Instagram } from "lucide-react";

export default function Footer() {
  return (
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
             <Link href="https://www.instagram.com/nimmiai.in?igsh=MWwyenN6ZGwyZDEzYw%3D%3D&utm_source=qr" target="_blank" rel="noopener noreferrer" className="w-8 h-8 rounded-full bg-zinc-50 flex items-center justify-center text-zinc-400 hover:text-[#9d55ac] transition-colors cursor-pointer"><Instagram size={16} /></Link>
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
            <li><Link href="mailto:support.nimmi@gmail.com" className="text-sm text-zinc-500 hover:text-[#9d55ac] transition-colors">Contact</Link></li>
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
  );
}
