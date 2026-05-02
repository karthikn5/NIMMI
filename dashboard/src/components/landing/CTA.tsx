import Link from "next/link";

export default function CTA() {
  return (
    <section className="px-4 sm:px-6 pb-16 sm:pb-24">
      <div className="max-w-5xl mx-auto relative overflow-hidden rounded-2xl sm:rounded-3xl bg-gradient-to-r from-[#6b2d7b] to-[#9d55ac] px-6 sm:px-8 md:px-16 py-10 sm:py-16 text-center">
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
      </div>
    </section>
  );
}
