import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, Clock, User, Share2, Facebook, Twitter, Linkedin } from "lucide-react";
import { Metadata } from "next";

const blogPosts = {
  "how-to-build-custom-ai-chatbot-2026": {
    title: "How to Build a Custom AI Chatbot for Your Business in 2026",
    content: `
      <p>In 2026, the landscape of customer interaction has completely shifted. Static FAQs are dead. Customers now expect immediate, personalized, and intelligent responses at any time of day. Building a <strong>custom AI chatbot</strong> is no longer just a luxury for large corporations—it's a necessity for any business in India looking to scale.</p>
      
      <h2>Step 1: Define Your Data Source</h2>
      <p>The soul of your AI assistant is your data. With Nimmi AI, you can train your bot on PDF documents, FAQs, website URLs, or even raw text. The goal is to provide your bot with a "brain" that contains all your product knowledge and business logic.</p>

      <h2>Step 2: Craft the Personality</h2>
      <p>A bot that sounds like a machine is a bot that users will ignore. Use our builder to define a persona. Is your bot a professional consultant? A friendly guide? Or a quirky shopping assistant? Setting the tone is crucial for brand alignment.</p>

      <h2>Step 3: Deploy and Iterate</h2>
      <p>Deploying is easy with a single line of code. But the real work starts after launch. Use our dashboard to monitor conversations, identify where the bot gets stuck, and fine-tune its knowledge base.</p>
    `,
    date: "May 2, 2026",
    author: "Nimmi AI Team",
    image: "/blog-1.png",
    category: "Tutorial"
  },
  "ai-chatbot-vs-live-chat-india": {
    title: "AI Chatbot vs Live Chat: Which is better for Indian Businesses?",
    content: `
      <p>Indian businesses are growing at a record pace, but scaling customer support remains a major challenge. Should you hire more people or invest in an AI chatbot?</p>
      
      <h2>The Human Element</h2>
      <p>Live chat provides empathy and handles complex, unique problems well. However, it's expensive to maintain 24/7 coverage and leads to long wait times during peak hours.</p>

      <h2>The AI Advantage</h2>
      <p>AI Chatbots provide instant responses, handle thousands of queries simultaneously, and never sleep. In India, where mobile usage is high, users expect instant gratification on platforms like WhatsApp and Web.</p>

      <h2>The Verdict</h2>
      <p>For most businesses, a hybrid approach is best. Use an <strong>AI chatbot for your website</strong> to handle 80% of routine queries, and hand off the remaining 20% to your human team for that personal touch.</p>
    `,
    date: "April 28, 2026",
    author: "Ananya Sharma",
    image: "/blog-2.png",
    category: "Comparison"
  },
  "calculating-chatbot-roi": {
    title: "Calculating the ROI of Your AI Chatbot: A Complete Guide",
    content: `
      <p>Is an AI chatbot worth the investment? Let's break down the numbers for a typical SME in India.</p>
      
      <h2>Cost Savings</h2>
      <p>The average support ticket costs between $5 to $15 when handled by a human. An AI chatbot can resolve these for cents. If your business handles 1,000 queries a month, you could be saving over $5,000 monthly.</p>

      <h2>Lead Generation ROI</h2>
      <p>Beyond support, chatbots are powerful lead magnets. By engaging visitors 24/7, businesses using Nimmi AI report a 35% increase in qualified leads compared to static contact forms.</p>

      <h2>Customer Lifetime Value</h2>
      <p>Better support leads to higher retention. A chatbot that solves a customer's problem in seconds increases trust and repeat purchases.</p>
    `,
    date: "April 20, 2026",
    author: "Rahul Varma",
    image: "/blog-3.png",
    category: "Business"
  }
};

export default function BlogPost({ params }: { params: { slug: string } }) {
  const post = blogPosts[params.slug as keyof typeof blogPosts];

  if (!post) return <div className="p-20 text-center">Post not found</div>;

  return (
    <div className="min-h-screen bg-white font-[family-name:var(--font-geist-sans)] pb-20">
      {/* Article Header */}
      <nav className="fixed top-0 left-0 right-0 bg-white/80 backdrop-blur-md border-b border-zinc-100 z-50">
        <div className="max-w-4xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link href="/blog" className="text-zinc-500 hover:text-[#9d55ac] flex items-center gap-2 text-sm font-medium">
            <ArrowLeft size={16} /> All Posts
          </Link>
          <div className="flex items-center gap-4">
             <button className="p-2 hover:bg-zinc-50 rounded-full transition-colors text-zinc-400 hover:text-[#9d55ac]"><Share2 size={18} /></button>
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
                   {post.author[0]}
                 </div>
                 <div>
                   <p className="text-sm font-bold text-zinc-900">{post.author}</p>
                   <p className="text-xs text-zinc-500">{post.date}</p>
                 </div>
               </div>
               <div className="flex items-center gap-2 text-xs text-zinc-400 font-medium">
                 <Clock size={14} /> 5 min read
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
            className="prose prose-purple max-w-none prose-p:text-zinc-600 prose-p:leading-relaxed prose-headings:text-zinc-900 prose-strong:text-zinc-900 prose-h2:text-3xl prose-h2:mt-12 prose-h2:mb-6"
            dangerouslySetInnerHTML={{ __html: post.content }}
          />
        </article>
      </main>

      {/* Recommended Section */}
      <section className="max-w-4xl mx-auto mt-20 px-6 pt-20 border-t border-zinc-100 text-center">
         <h3 className="text-2xl font-bold mb-4">Start building your story</h3>
         <p className="text-zinc-500 mb-8 max-w-md mx-auto">Join thousands of businesses scaling their support with Nimmi AI.</p>
         <Link href="/auth/signup" className="inline-flex px-8 py-3 bg-[#9d55ac] text-white rounded-xl font-bold hover:bg-[#8a4a97] transition-all shadow-lg shadow-purple-500/20">
           Build Your Bot Free
         </Link>
      </section>
    </div>
  );
}
