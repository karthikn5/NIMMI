import type { Metadata } from "next";
import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, Clock, ChevronRight } from "lucide-react";
import JsonLd from "@/components/site/JsonLd";
import { POSTS, displayDate, readMinutes } from "@/lib/site/blog";
import { SITE, absolute, breadcrumbLd, pageMetadata } from "@/lib/site/seo";

const DESCRIPTION = "Guides on AI voice agents, WhatsApp chatbots, website chatbots and lead follow-up for Indian businesses, including TRAI's calling rules.";

export const metadata: Metadata = pageMetadata({
  title: "Blog: AI Voice Agents and Chatbots",
  description: DESCRIPTION,
  path: "/blog",
});

export default function BlogIndex() {
  return (
    <div className="min-h-screen bg-[#faf9f7] font-[family-name:var(--font-geist-sans)]">
      <JsonLd data={[breadcrumbLd([["Home", "/"], ["Blog", "/blog"]]), {
        "@context": "https://schema.org", "@type": "Blog", name: `${SITE.name} Blog`, url: absolute("/blog"), description: DESCRIPTION,
        publisher: { "@id": `${SITE.url}/#organization` },
        blogPost: POSTS.map((p) => ({ "@type": "BlogPosting", headline: p.title, url: absolute(`/blog/${p.slug}`), datePublished: p.published })),
      }]} />
      {/* Header */}
      <header className="bg-white border-b border-zinc-100 py-12 px-6">
        <div className="max-w-7xl mx-auto">
          <Link href="/" className="inline-flex items-center gap-2 text-zinc-500 hover:text-[#9d55ac] transition-colors mb-8 group">
            <ArrowLeft size={18} className="group-hover:-translate-x-1 transition-transform" />
            Back to Home
          </Link>
          <h1 className="text-4xl md:text-6xl font-bold text-zinc-900 mb-4">
            Nimmi AI <span className="text-[#9d55ac]">Resources</span>
          </h1>
          <p className="text-zinc-500 text-lg max-w-2xl">
            Expert insights, tutorials, and guides to help you build better AI experiences for your customers.
          </p>
        </div>
      </header>

      {/* Blog Grid */}
      <main className="max-w-7xl mx-auto py-16 px-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {POSTS.map((post) => (
            <Link 
              key={post.slug} 
              href={`/blog/${post.slug}`}
              className="group bg-white rounded-3xl border border-zinc-100 overflow-hidden hover:shadow-2xl hover:shadow-purple-500/10 hover:border-purple-200 transition-all flex flex-col"
            >
              <div className="relative h-56 w-full bg-purple-50 overflow-hidden">
                {/* Fallback pattern if image is missing */}
                <div className="absolute inset-0 bg-gradient-to-br from-purple-100 to-white flex items-center justify-center">
                   <span className="text-purple-300 font-bold text-lg">{post.category}</span>
                </div>
                <Image 
                  src={post.image} 
                  alt={post.title} 
                  fill 
                  className="object-cover group-hover:scale-105 transition-transform duration-500"
                />
              </div>
              <div className="p-8 flex-1 flex flex-col">
                <div className="flex items-center gap-4 text-xs font-bold text-purple-400 uppercase tracking-widest mb-4">
                  <span>{post.category}</span>
                  <span className="w-1 h-1 rounded-full bg-zinc-200" />
                  <span className="flex items-center gap-1"><Clock size={12} /> {readMinutes(post)} min read</span>
                </div>
                <h2 className="text-xl font-bold text-zinc-900 mb-3 group-hover:text-[#9d55ac] transition-colors line-clamp-2">
                  {post.title}
                </h2>
                <p className="text-zinc-500 text-sm leading-relaxed mb-6 line-clamp-3">
                  {post.description}
                </p>
                <div className="mt-auto pt-6 border-t border-zinc-50 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-full bg-zinc-100 flex items-center justify-center text-xs font-bold text-zinc-400">
                      N
                    </div>
                    <span className="text-xs font-medium text-zinc-600">{displayDate(post.published)}</span>
                  </div>
                  <ChevronRight size={18} className="text-zinc-300 group-hover:text-[#9d55ac] group-hover:translate-x-1 transition-all" />
                </div>
              </div>
            </Link>
          ))}
        </div>
      </main>

      {/* CTA Section */}
      <section className="py-20 px-6">
        <div className="max-w-4xl mx-auto bg-gradient-to-r from-[#6b2d7b] to-[#9d55ac] rounded-[3rem] p-12 text-center text-white relative overflow-hidden">
           <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 blur-3xl rounded-full -mr-16 -mt-16" />
           <h2 className="text-3xl font-bold mb-4">Want to build your own bot?</h2>
           <p className="text-purple-100 mb-8 max-w-md mx-auto">Build and test your assistant for website chat, WhatsApp and phone calls, free. No card needed.</p>
           <Link href="/auth/signup" className="inline-flex px-8 py-3 bg-white text-[#9d55ac] rounded-xl font-bold hover:bg-zinc-50 transition-all shadow-xl">
             Get Started for Free
           </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 border-t border-zinc-100 text-center">
        <p className="text-sm text-zinc-400">© 2026 Nimmi AI. Empowering businesses through conversational AI.</p>
      </footer>
    </div>
  );
}
