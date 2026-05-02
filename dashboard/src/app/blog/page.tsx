import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, Clock, User, ChevronRight } from "lucide-react";

const blogPosts = [
  {
    slug: "how-to-build-custom-ai-chatbot-2026",
    title: "How to Build a Custom AI Chatbot for Your Business in 2026",
    excerpt: "Learn the step-by-step process of creating an AI assistant that understands your business data and delights your customers.",
    date: "May 2, 2026",
    author: "Nimmi AI Team",
    image: "/blog-1.png",
    category: "Tutorial"
  },
  {
    slug: "ai-chatbot-vs-live-chat-india",
    title: "AI Chatbot vs Live Chat: Which is better for Indian Businesses?",
    excerpt: "Comparing the costs, response times, and scalability of automated AI assistants vs traditional live chat support teams.",
    date: "April 28, 2026",
    author: "Ananya Sharma",
    image: "/blog-2.png",
    category: "Comparison"
  },
  {
    slug: "calculating-chatbot-roi",
    title: "Calculating the ROI of Your AI Chatbot: A Complete Guide",
    excerpt: "Discover how much money your business can save by automating customer interactions and boosting lead generation.",
    date: "April 20, 2026",
    author: "Rahul Varma",
    image: "/blog-3.png",
    category: "Business"
  }
];

export default function BlogIndex() {
  return (
    <div className="min-h-screen bg-[#faf9f7] font-[family-name:var(--font-geist-sans)]">
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
          {blogPosts.map((post) => (
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
                  <span className="flex items-center gap-1"><Clock size={12} /> 5 min read</span>
                </div>
                <h2 className="text-xl font-bold text-zinc-900 mb-3 group-hover:text-[#9d55ac] transition-colors line-clamp-2">
                  {post.title}
                </h2>
                <p className="text-zinc-500 text-sm leading-relaxed mb-6 line-clamp-3">
                  {post.excerpt}
                </p>
                <div className="mt-auto pt-6 border-t border-zinc-50 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-full bg-zinc-100 flex items-center justify-center text-xs font-bold text-zinc-400">
                      {post.author[0]}
                    </div>
                    <span className="text-xs font-medium text-zinc-600">{post.author}</span>
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
           <p className="text-purple-100 mb-8 max-w-md mx-auto">Join 1,000+ businesses using Nimmi AI to automate their customer service today.</p>
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
