import { HelpCircle } from "lucide-react";

const faqs = [
  {
    question: "What is an AI Chatbot and how does Nimmi AI work?",
    answer: "An AI chatbot is an intelligent virtual assistant capable of understanding natural language and engaging in human-like conversations. Nimmi AI is a specialized custom AI chatbot builder India trusts. It works by analyzing the data you provide—such as PDFs, website URLs, or text documents—and using large language models to generate accurate, context-aware responses to your users' queries in real-time."
  },
  {
    question: "Do I need coding skills to use Nimmi AI?",
    answer: "Absolutely not! Nimmi AI is designed specifically as a no-code required platform. You don't need any programming knowledge or technical background to build your own AI chatbot. Simply upload your data, customize the appearance of the chat widget, and copy-paste a small snippet of code onto your website. It is the easiest chatbot builder India has to offer."
  },
  {
    question: "How secure is the data I use to train the AI?",
    answer: "Data security is our top priority. The documents, URLs, and texts you upload to train your custom AI chatbot are encrypted and stored securely. We do not use your private business data to train public foundation models. Your knowledge base remains entirely yours, ensuring that your confidential information and customer interactions are fully protected."
  },
  {
    question: "What platforms can I integrate my custom chatbot with?",
    answer: "Nimmi AI chatbots are highly versatile. You can embed them on almost any website platform including WordPress, Shopify, Wix, Webflow, and custom HTML/JS sites. In addition to web widgets, we are continuously expanding our integration capabilities to connect your custom AI chatbot with popular messaging platforms like WhatsApp, Telegram, and Facebook Messenger."
  },
  {
    question: "How much does it cost to build a chatbot?",
    answer: "We offer a flexible pricing structure to suit businesses of all sizes. You can start completely free with our generous Free Forever plan to build your own AI chatbot and test its capabilities. As your traffic and requirements grow, you can seamlessly upgrade to our premium plans which offer higher message limits, advanced analytics, and priority support."
  }
];

export default function FAQ() {
  return (
    <section id="faq" className="py-16 sm:py-24 px-4 sm:px-6 bg-[#faf9f7]">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-purple-50 border border-purple-100 rounded-full mb-6">
            <HelpCircle size={14} className="text-[#9d55ac]" />
            <span className="text-sm font-medium text-[#9d55ac]">Frequently Asked Questions</span>
          </div>
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold leading-tight mb-4">
            Everything you need to know about<br />our <span className="text-[#9d55ac]">Chatbot Builder</span>
          </h2>
          <p className="text-zinc-500 text-lg max-w-2xl mx-auto">
            Find answers to common questions about creating, training, and deploying a custom AI chatbot for your website without any coding.
          </p>
        </div>

        <div className="space-y-6">
          {faqs.map((faq, i) => (
            <div key={i} className="bg-white p-6 sm:p-8 rounded-2xl shadow-sm border border-zinc-100">
              <h3 className="text-xl font-bold text-zinc-900 mb-3">{faq.question}</h3>
              <p className="text-zinc-600 leading-relaxed">{faq.answer}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
