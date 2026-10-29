import Link from "next/link";
import Image from "next/image";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowUpRight, Clock, Share2 } from "lucide-react";
import { Metadata } from "next";
import JsonLd from "@/components/site/JsonLd";
import { PAGES } from "@/components/site/PageParts";
import { POSTS, displayDate, postBySlug, readMinutes } from "@/lib/site/blog";
import { absolute, articleLd, breadcrumbLd, pageMetadata } from "@/lib/site/seo";

type Params = Promise<{ slug: string }>;

export function generateStaticParams() {
  return POSTS.map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const post = postBySlug((await params).slug);
  if (!post) return { title: "Post not found", robots: { index: false } };
  return pageMetadata({
    title: post.seoTitle, description: post.description, path: `/blog/${post.slug}`, image: post.image,
    type: "article", publishedTime: post.published,
  });
}

const PRODUCT_PAGES = Object.values(PAGES);

export default async function BlogPost({ params }: { params: Params }) {
  const post = postBySlug((await params).slug);
  if (!post) notFound();
  const path = `/blog/${post.slug}`;
  const share = `https://wa.me/?text=${encodeURIComponent(`${post.title} ${absolute(path)}`)}`;
  const related = PRODUCT_PAGES.filter((p) => post.related.includes(p.href));
  const more = POSTS.filter((p) => p.slug !== post.slug).slice(0, 3);

  return (
    <div className="min-h-screen bg-white font-[family-name:var(--font-geist-sans)] pb-20">
      <JsonLd data={[
        articleLd({ title: post.title, description: post.description, path, image: post.image, published: post.published }),
        breadcrumbLd([["Home", "/"], ["Blog", "/blog"], [post.title, path]]),
      ]} />
      {/* Article Header */}
      <nav className="fixed top-0 left-0 right-0 bg-white/80 backdrop-blur-md border-b border-zinc-100 z-50">
        <div className="max-w-4xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link href="/blog" className="text-zinc-500 hover:text-[#9d55ac] flex items-center gap-2 text-sm font-medium">
            <ArrowLeft size={16} /> All Posts
          </Link>
          <div className="flex items-center gap-4">
             <a href={share} target="_blank" rel="noopener noreferrer" aria-label="Share on WhatsApp"
                className="p-2 hover:bg-zinc-50 rounded-full transition-colors text-zinc-400 hover:text-[#9d55ac]"><Share2 size={18} /></a>
          </div>
        </div>
      </nav>

      <main className="pt-24 px-6">
        <article className="max-w-3xl mx-auto">
          <header className="mb-12">
            <div className="inline-block px-4 py-1 bg-purple-50 text-purple-600 rounded-full text-xs font-bold uppercase tracking-widest mb-6">
              {post.category}
            </div>
            <h1 className="text-3xl md:text-5xl font-bold text-zinc-900 leading-tight mb-8">
              {post.title}
            </h1>
            <div className="flex items-center justify-between py-6 border-y border-zinc-100">
               <div className="flex items-center gap-3">
                 <div className="w-10 h-10 rounded-full bg-purple-100 flex items-center justify-center font-bold text-purple-600">
                   N
                 </div>
                 <div>
                   <p className="text-sm font-bold text-zinc-900">Nimmi AI Team</p>
                   <p className="text-xs text-zinc-500"><time dateTime={post.published}>{displayDate(post.published)}</time></p>
                 </div>
               </div>
               <div className="flex items-center gap-2 text-xs text-zinc-400 font-medium">
                 <Clock size={14} /> {readMinutes(post)} min read
               </div>
            </div>
          </header>

          <div className="relative aspect-video w-full rounded-3xl overflow-hidden mb-12 shadow-2xl">
            <Image
              src={post.image}
              alt={post.title}
              fill
              className="object-cover"
              priority
            />
          </div>

          <div
            className="prose prose-purple max-w-none prose-p:text-zinc-600 prose-p:leading-relaxed prose-headings:text-zinc-900 prose-strong:text-zinc-900 prose-h2:text-3xl prose-h2:mt-12 prose-h2:mb-6 prose-a:text-[#9d55ac]"
            dangerouslySetInnerHTML={{ __html: post.content }}
          />

          {related.length > 0 && (
            <aside className="mt-14 pt-8 border-t border-zinc-100">
              <h2 className="text-sm font-bold text-zinc-900 uppercase tracking-widest mb-4">In Nimmi AI</h2>
              <ul className="grid sm:grid-cols-2 gap-4">
                {related.map((p) => (
                  <li key={p.href}>
                    <Link href={p.href} className="group block h-full p-5 rounded-2xl border border-zinc-100 hover:border-purple-200 hover:shadow-lg transition-all">
                      <span className="inline-flex items-center gap-1 font-bold text-zinc-900 group-hover:text-[#9d55ac]">{p.name} <ArrowUpRight size={14} /></span>
                      <span className="block text-sm text-zinc-500 mt-1 leading-relaxed">{p.text}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </aside>
          )}
        </article>
      </main>

      {/* More posts */}
      <section className="max-w-4xl mx-auto mt-16 px-6">
        <h2 className="text-sm font-bold text-zinc-900 uppercase tracking-widest mb-4">More from the blog</h2>
        <ul className="divide-y divide-zinc-100 border-y border-zinc-100">
          {more.map((p) => (
            <li key={p.slug}>
              <Link href={`/blog/${p.slug}`} className="flex items-center justify-between gap-4 py-4 text-zinc-700 hover:text-[#9d55ac]">
                <span className="font-medium">{p.title}</span>
                <span className="text-xs text-zinc-400 whitespace-nowrap">{displayDate(p.published)}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      {/* Recommended Section */}
      <section className="max-w-4xl mx-auto mt-20 px-6 pt-20 border-t border-zinc-100 text-center">
         <h3 className="text-2xl font-bold mb-4">Start building your story</h3>
         <p className="text-zinc-500 mb-8 max-w-md mx-auto">Build an assistant for your website, WhatsApp and phone calls, free. No card needed.</p>
         <Link href="/auth/signup" className="inline-flex px-8 py-3 bg-[#9d55ac] text-white rounded-xl font-bold hover:bg-[#8a4a97] transition-all shadow-lg shadow-purple-500/20">
           Build Your Bot Free
         </Link>
      </section>
    </div>
  );
}
