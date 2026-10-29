/** The blog's posts: one list for the index, each post's page, the sitemap and search engines. Newest first. */

export type Post = {
    slug: string;
    title: string;         // the headline
    seoTitle: string;      // the search result's title: under about 60 characters with " | Nimmi AI"
    description: string;   // the search snippet and the card's text, 120-160 characters
    published: string;     // ISO date
    category: string;
    image: string;
    related: string[];     // product pages it leads to (paths)
    content: string;       // HTML
};

export const POSTS: Post[] = [
    {
        slug: "ai-calling-rules-india-trai",
        title: "Is AI Calling Legal in India? TRAI Rules for AI Voice Agents (2026)",
        seoTitle: "Is AI Calling Legal in India? TRAI Rules 2026",
        description: "What India's TRAI rules mean for AI voice agents in 2026: consent, the 140 and 160 number series, opt-outs, DND and complaints, explained in plain English.",
        published: "2026-10-29",
        category: "Compliance",
        image: "/blog/ai-calling-rules-india-trai.png",
        related: ["/ai-voice-agent", "/lead-management"],
        content: `
      <p>Short answer: yes. A business in India can use an AI voice agent to answer calls and to call customers, as long as it follows the same rules as any other business caller. Those rules come from the Telecom Regulatory Authority of India (TRAI), in the Telecom Commercial Communications Customer Preference Regulations (TCCCPR), which an amendment tightened in February 2025.</p>
      <p>This guide explains what the rules mean for AI calls in plain English. It isn't legal advice: for your own business, confirm the details with your telecom provider or a lawyer.</p>

      <h2>Answering calls with AI</h2>
      <p>When a customer calls you, an AI receptionist can answer. Good practice, and what Nimmi does on every call, is to say at the start that the caller is speaking with an automated assistant and that the call may be recorded. Then the caller knows what they're talking to, and can ask for a person.</p>

      <h2>Calling customers: consent comes first</h2>
      <p>Outgoing calls are where the rules matter. TRAI separates commercial calls into two kinds:</p>
      <ul>
        <li><strong>Promotional calls</strong> sell or advertise something.</li>
        <li><strong>Service and transactional calls</strong> are about something the customer is already doing with you, like a booking, an order or an enquiry they made.</li>
      </ul>
      <p>Under the 2025 amendment, explicit consent for service calls lasts at most seven days unless TRAI directs otherwise. If promotional content is mixed into a service call, the whole call counts as promotional. In practice: call people back about what they asked for, soon after they asked, and keep sales pitches out of service calls.</p>

      <h2>The right number series</h2>
      <p>Promotional calls must come from numbers in the 140 series. Service and transactional calls are moving to the 160 series. Using an ordinary 10-digit mobile number for commercial calls can lead to all of a sender's telecom resources being disconnected for up to two years. Ask your telecom provider which series your calls should use before you start calling lists.</p>

      <h2>Do Not Disturb and opt-outs</h2>
      <p>Promotional calls can't go to numbers on the national Do Not Disturb (DND) registry unless the person has given you explicit consent. When someone asks you to stop calling, stop, and keep a do-not-call list of your own. After an opt-out, you can't ask that person for consent again for 90 days.</p>

      <h2>Complaints add up quickly</h2>
      <p>The amendment lowered the bar for action: five valid complaints within ten days are enough. Penalties start with a temporary bar on outgoing calls and go up to disconnection and blacklisting for repeat offences. Calling only people who want to hear from you is also simply better business.</p>

      <h2>A checklist for AI calls in India</h2>
      <ul>
        <li>Say the call is automated and may be recorded, at the start of every call.</li>
        <li>Call only people who asked for a call or agreed to one, and record when and how they agreed.</li>
        <li>Keep follow-ups inside the consent window: stop about a week after their last conversation, unless they agreed to more.</li>
        <li>Honour "don't call me" at once, and keep a do-not-call list.</li>
        <li>Use the number series your provider gives you for each kind of call.</li>
        <li>Keep calls to sensible hours, and skip holidays.</li>
        <li>Delete recordings when you no longer need them.</li>
      </ul>

      <h2>How Nimmi handles it</h2>
      <p>Nimmi's <a href="/ai-voice-agent">AI voice agent</a> says it's automated and may be recorded on every call, honours opt-out phrases and adds the number to your do-not-call list, and only dials people who asked to be called or were on a list you confirmed they agreed to. Its <a href="/lead-management">follow-ups</a> stop seven days after someone's last conversation by default, stay inside the calling hours and days you set, and record why each call was allowed.</p>

      <p class="sources">Sources: TRAI's TCCCPR 2018 and its February 2025 amendment, as summarised by <a href="https://www.sigmachambers.in/post/2025-tcccpr-amendments-a-renewed-push-by-trai-for-order-in-commercial-communications-1" rel="noopener" target="_blank">Sigma Chambers</a> and <a href="https://rootle.ai/blog/the-february-2025-trai-amendment-voice-ai-compliance/" rel="noopener" target="_blank">Rootle</a>. Details vary between summaries, so check the current text with your provider.</p>
    `,
    },
    {
        slug: "what-is-an-ai-voice-agent",
        title: "What Is an AI Voice Agent? How AI Phone Calls Work for Indian Businesses",
        seoTitle: "What Is an AI Voice Agent? A Guide for India",
        description: "An AI voice agent answers and makes phone calls like a person. How it works, which Indian languages it speaks, what it costs and where it helps a business.",
        published: "2026-10-27",
        category: "Guide",
        image: "/blog/what-is-an-ai-voice-agent.png",
        related: ["/ai-voice-agent", "/pricing"],
        content: `
      <p>An AI voice agent is software that talks on the phone the way a person does. It picks up a call, listens to what the caller says, works out what they need and answers in a natural voice. It can also make calls: calling back a lead, confirming an appointment or following up after an enquiry.</p>
      <p>For Indian businesses, the interesting part is that today's voice agents can do this in Tamil, Hindi, Telugu and other Indian languages, and keep up when a caller mixes in English.</p>

      <h2>How an AI phone call works</h2>
      <p>Every turn of the conversation goes through three steps, usually in about a second:</p>
      <ul>
        <li><strong>Listening.</strong> Speech recognition turns the caller's voice into text, as they speak.</li>
        <li><strong>Understanding.</strong> A language model reads the text with your business information and the conversation so far, and writes the reply.</li>
        <li><strong>Speaking.</strong> A text-to-speech voice says the reply, starting before the whole answer is even written.</li>
      </ul>
      <p>The agent can be interrupted, like a person: if the caller starts talking, it stops and listens. It can also look things up during the call, such as an order's status or a free appointment slot, if you connect it to your systems.</p>

      <h2>How it differs from an IVR</h2>
      <p>An IVR plays a menu: "press 1 for sales". Callers have to fit their question into your menu, and many hang up. A voice agent lets them simply say what they want, in their own words and language, and answers it. When it can't, it passes the call to a person with a short summary.</p>

      <h2>What an AI voice agent can do</h2>
      <ul>
        <li>Answer every incoming call, day and night, as an AI receptionist.</li>
        <li>Call back new leads within a minute of their enquiry.</li>
        <li>Ask qualifying questions, like budget, location or preferred date.</li>
        <li>Book appointments, site visits and meetings.</li>
        <li>Follow up with leads who haven't decided yet.</li>
        <li>Transfer to your team when a caller wants a person.</li>
        <li>Record, transcribe and summarise every call.</li>
      </ul>

      <h2>Where it helps most</h2>
      <p>Any business that misses calls or calls leads back too late. Real estate developers answering project enquiries, clinics booking appointments, coaching institutes handling admission questions, and online stores confirming cash-on-delivery orders are common examples.</p>

      <h2>What it costs</h2>
      <p>Voice agents are usually priced per minute. On Nimmi, a call minute is 1 credit plus the rate of the AI model you choose, counted in half-minutes. With a quick model, a minute works out to about ₹5 at the 1,000-credit pack price. See <a href="/pricing">pricing</a> for the current rates.</p>

      <h2>How to start</h2>
      <p>Add your business information, choose a language and a voice, and test the agent in your browser or on your own phone. When it sounds right, connect a phone number. Nimmi's <a href="/ai-voice-agent">AI voice agent</a> is free to try, with 10 call credits.</p>
    `,
    },
    {
        slug: "speed-to-lead-call-back-in-5-minutes",
        title: "Speed to Lead: Why Calling Back Within 5 Minutes Wins Customers",
        seoTitle: "Speed to Lead: Call Back Leads in 5 Minutes",
        description: "Leads called back within five minutes are far likelier to buy. What research says, how many follow-ups to make, and how to automate it within TRAI rules.",
        published: "2026-10-25",
        category: "Sales",
        image: "/blog/speed-to-lead-call-back-in-5-minutes.png",
        related: ["/lead-management", "/ai-voice-agent"],
        content: `
      <p>When someone fills your enquiry form or asks for a call, they are thinking about you right now. Ten minutes later they are on another website, or another call. That is the idea behind "speed to lead": the faster you respond, the likelier you are to win the customer.</p>

      <h2>What the research says</h2>
      <p>The figure quoted most often is that leads reached within five minutes are about 21 times likelier to become qualified than leads reached after 30 minutes. Yet only about 7% of companies respond within five minutes, and around half of leads are never contacted at all. These numbers come from sales-software vendors' studies, so treat them as a direction rather than a promise, but every study points the same way.</p>

      <h2>One call is not enough</h2>
      <p>Persistence matters as much as speed. When InsideSales audited what salespeople actually did, reps made about four attempts per lead, while they believed they made twelve or more. A widely cited study of 3.5 million leads found that most converted leads were reached by the sixth call. The lesson: plan several follow-ups, spaced out, instead of one call and a forgotten spreadsheet.</p>

      <h2>A practical plan for Indian businesses</h2>
      <ul>
        <li><strong>Answer at once.</strong> Website chat and WhatsApp enquiries should get a reply in seconds, at any hour.</li>
        <li><strong>Call back within minutes.</strong> When someone asks for a call, ring them while they are still interested.</li>
        <li><strong>Follow up by interest.</strong> A hot lead deserves a call the next day or two; a cold one, a single check-in later.</li>
        <li><strong>Remember the last conversation.</strong> Start each follow-up where the last one ended, instead of asking the same questions.</li>
        <li><strong>Stop when asked.</strong> Respect opt-outs and India's calling rules: follow up about what they asked for, within about a week.</li>
      </ul>

      <h2>Automating it</h2>
      <p>Doing this by hand means someone watching the enquiry inbox all day. Nimmi's <a href="/lead-management">AI lead management</a> does it for you: it answers chats instantly, calls back within a minute, rates each lead hot, warm or cold after every call, and plans the next call by your rules, with what to say. When a lead wants to meet your team, it books the meeting on your free times for you to approve.</p>

      <p class="sources">Sources: <a href="https://www.kixie.com/sales-blog/speed-to-lead-response-time-statistics-that-drive-conversions/" rel="noopener" target="_blank">Kixie</a>, <a href="https://www.insidesales.com/blog/perfect-sales-cadence" rel="noopener" target="_blank">InsideSales</a>, <a href="https://instantly.ai/blog/how-many-times-should-you-really-follow-up-with-a-prospect/" rel="noopener" target="_blank">Instantly</a>. Figures are from vendor research.</p>
    `,
    },
    {
        slug: "whatsapp-chatbot-for-business-india",
        title: "WhatsApp Chatbot for Business in India: A Practical Guide (2026)",
        seoTitle: "WhatsApp Chatbot for Business in India: 2026 Guide",
        description: "How a WhatsApp chatbot works on the WhatsApp Business Platform, the 24-hour window, templates and charges, voice notes, and handing chats to your team.",
        published: "2026-10-22",
        category: "Guide",
        image: "/blog/whatsapp-chatbot-for-business-india.png",
        related: ["/whatsapp-chatbot", "/pricing"],
        content: `
      <p>Most Indian customers would rather message a business on WhatsApp than fill a form or wait on hold. A WhatsApp chatbot answers those messages instantly, on your own business number, and brings in your team when a person is needed. Here is what you need to know before you set one up.</p>

      <h2>The WhatsApp Business app and the Business Platform</h2>
      <p>The free WhatsApp Business app is made for one phone and a person typing. To answer automatically, a chatbot uses Meta's WhatsApp Business Platform (often called the WhatsApp Business API), connected to your business number. Your customers see the same number and name either way.</p>

      <h2>The 24-hour window</h2>
      <p>When a customer messages you, a 24-hour customer service window opens. Inside it, your chatbot and your team can reply freely, and those replies are free. Outside it, you can only start a conversation with an approved template message, such as an appointment reminder or an order update, and Meta charges for templates by category.</p>

      <h2>What to automate first</h2>
      <ul>
        <li>The questions you answer every day: prices, timings, location, availability.</li>
        <li>Sending your brochure, price list or menu when someone asks.</li>
        <li>Collecting enquiry details: name, what they want, budget, preferred date.</li>
        <li>Booking requests and call-back requests.</li>
        <li>Handing over to a person for complaints, negotiations and anything unusual.</li>
      </ul>

      <h2>Make it feel human</h2>
      <p>People send three short messages in a row, voice notes and photos. A good WhatsApp chatbot waits until they finish typing, shows that it's typing, and answers in short messages. It should listen to voice notes, read the photos and PDFs customers send, and reply in the language and script they wrote in, including Tanglish and Hinglish.</p>

      <h2>Meta's rules for AI on WhatsApp</h2>
      <p>Since January 2026, Meta's policies don't allow general-purpose AI chatbots on the WhatsApp Business Platform. Assistants that serve a business's own customers, answering about its products and services, are allowed. Build your chatbot around your business, not as a general assistant.</p>

      <h2>Mistakes to avoid</h2>
      <ul>
        <li>Walls of text. Keep each message short.</li>
        <li>No way out. Customers should always be able to reach a person.</li>
        <li>Two answers at once. When your team replies, the bot should step back on that chat.</li>
        <li>Ignoring opt-outs. When someone says stop, stop messaging them.</li>
      </ul>

      <p>Nimmi's <a href="/whatsapp-chatbot">WhatsApp AI chatbot</a> does all of this on your own number, with your team's inbox alongside. See <a href="/pricing">pricing</a> to get started.</p>
    `,
    },
    {
        slug: "how-to-build-custom-ai-chatbot-2026",
        title: "How to Build a Custom AI Chatbot for Your Business in 2026",
        seoTitle: "How to Build a Custom AI Chatbot in 2026",
        description: "A step-by-step guide to building a custom AI chatbot trained on your business data: what to teach it, how to set its tone, and how to launch and improve it.",
        published: "2026-05-02",
        category: "Tutorial",
        image: "/blog-1.png",
        related: ["/ai-chatbot-for-website", "/whatsapp-chatbot"],
        content: `
      <p>In 2026, the landscape of customer interaction has completely shifted. Static FAQs are dead. Customers now expect immediate, personalized, and intelligent responses at any time of day. Building a <strong>custom AI chatbot</strong> is no longer just a luxury for large corporations: it's a necessity for any business in India looking to scale.</p>

      <h2>Step 1: Define Your Data Source</h2>
      <p>The soul of your AI assistant is your data. With Nimmi AI, you can train your bot on PDF documents, FAQs, website URLs, or even raw text. The goal is to provide your bot with a "brain" that contains all your product knowledge and business logic.</p>

      <h2>Step 2: Craft the Personality</h2>
      <p>A bot that sounds like a machine is a bot that users will ignore. Use our builder to define a persona. Is your bot a professional consultant? A friendly guide? Or a quirky shopping assistant? Setting the tone is crucial for brand alignment.</p>

      <h2>Step 3: Deploy and Iterate</h2>
      <p>Deploying is easy with a single line of code. But the real work starts after launch. Use our dashboard to monitor conversations, identify where the bot gets stuck, and fine-tune its knowledge base.</p>

      <p>Ready to build yours? Start with Nimmi's <a href="/ai-chatbot-for-website">custom AI chatbot for websites</a>, and add <a href="/whatsapp-chatbot">WhatsApp</a> when you're ready.</p>
    `,
    },
    {
        slug: "ai-chatbot-vs-live-chat-india",
        title: "AI Chatbot vs Live Chat: Which is better for Indian Businesses?",
        seoTitle: "AI Chatbot vs Live Chat for Indian Businesses",
        description: "Comparing AI chatbots and live chat for Indian businesses: cost, response time, availability and when a person should take over the conversation.",
        published: "2026-04-28",
        category: "Comparison",
        image: "/blog-2.png",
        related: ["/ai-chatbot-for-website", "/whatsapp-chatbot"],
        content: `
      <p>Indian businesses are growing at a record pace, but scaling customer support remains a major challenge. Should you hire more people or invest in an AI chatbot?</p>

      <h2>The Human Element</h2>
      <p>Live chat provides empathy and handles complex, unique problems well. However, it's expensive to maintain 24/7 coverage and leads to long wait times during peak hours.</p>

      <h2>The AI Advantage</h2>
      <p>AI Chatbots provide instant responses, handle many conversations at once, and never sleep. In India, where mobile usage is high, users expect instant replies on platforms like WhatsApp and the web.</p>

      <h2>The Verdict</h2>
      <p>For most businesses, a hybrid approach is best. Use an <a href="/ai-chatbot-for-website">AI chatbot for your website</a> and WhatsApp to handle the routine questions, and hand the rest to your team for that personal touch. With Nimmi, the chat moves to your team's Live chat the moment a customer asks for a person.</p>
    `,
    },
    {
        slug: "calculating-chatbot-roi",
        title: "Calculating the ROI of Your AI Chatbot: A Complete Guide",
        seoTitle: "AI Chatbot ROI: How to Calculate It",
        description: "How to work out whether an AI chatbot pays for itself: the time it saves your team, the leads it captures and the customers it keeps, with an example.",
        published: "2026-04-20",
        category: "Business",
        image: "/blog-3.png",
        related: ["/pricing", "/ai-chatbot-for-website"],
        content: `
      <p>Is an AI chatbot worth the investment? Let's break down the numbers for a typical small business in India.</p>

      <h2>Cost Savings</h2>
      <p>Start with what a routine conversation costs you today. As an example, if a support executive costs ₹25,000 a month and handles about 40 conversations a day, each conversation costs roughly ₹25 of their time. Every routine question a chatbot answers saves that, and the chatbot answers at night and on Sundays too. Put your own salary and volume into the same sum.</p>

      <h2>Lead Generation ROI</h2>
      <p>Beyond support, chatbots are powerful lead magnets. A chatbot that answers at once and asks for contact details at the right moment usually captures more enquiries than a static contact form. Measure it: compare leads per 100 visitors for a month before and a month after.</p>

      <h2>Customer Lifetime Value</h2>
      <p>Better support leads to higher retention. A chatbot that solves a customer's problem in seconds increases trust and repeat purchases.</p>

      <p>Compare the savings with Nimmi's <a href="/pricing">pricing</a>: plans start at ₹833 a month billed yearly, and you can build and test free.</p>
    `,
    },
];

export function postBySlug(slug: string) {
    return POSTS.find((p) => p.slug === slug);
}

export function readMinutes(post: Post) {
    const words = post.content.replace(/<[^>]+>/g, " ").split(/\s+/).filter(Boolean).length;
    return Math.max(2, Math.round(words / 200));
}

export function displayDate(iso: string) {
    return new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
}
