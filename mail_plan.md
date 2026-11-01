# Email by Nimmi: plan

Written 1 Nov 2026 from the owner's idea, with market research. The owner's two starting points:

1. When someone gives their email on the website chat, Nimmi sends a welcome email the business can change, with its
   files (brochure, price list): "Hi Karthi, thanks for showing interest in our company. Someone from our team will
   connect with you shortly."
2. After an incoming or outgoing call, Nimmi emails what the person needs from the call: the meeting that was booked,
   the answers to their questions, the next step.

And the brief around them: think like a business that lives on its leads; take Salesforce as the example and shape it
for Nimmi's customers; include every option that keeps a lead engaged; build it in phases 0, 1, 2 and on.

Who reads what: the owner, sections 0, 3, 4, 8 and 10 (what customers get, one lead's story, prices, decisions);
whoever builds it, sections 1, 5, 6 and 7 (today's code, the full list, the building blocks, each phase's checks).

## 0. In one page

What we build:
- **Every conversation ends with a useful email.** After a chat, a call, a WhatsApp chat or a meeting: written from
  what was said, with the business's files, in the person's language, under the business's name (and from its own
  domain once connected).
- **Every reply comes back to Nimmi.** Replies land on the same contact as the person's calls and chats. The AI
  answers what the knowledge covers, books the meeting or call-back they ask for, and passes the rest to the team.
  Every follow-up stops the moment they reply.
- **Follow-ups across channels.** Email, WhatsApp and calls in one plan per lead (a journey), chosen by the lead's
  status, stopping when they book, reply or say stop.
- **Leads from anywhere.** Lead emails from IndiaMART, JustDial, property portals and website forms are forwarded to
  Nimmi; each lead gets an email at once and a call within minutes.
- **An honest view.** Who replied, clicked, downloaded, booked; which emails work; whether mail is landing; consent and
  unsubscribe records.

Why Nimmi can win (section 2): Salesforce does all of this with several products, an admin and per-user prices;
Indian CRMs (Zoho, Freshsales, LeadSquared) charge per user and don't talk to callers; voice AI platforms leave the
follow-up email to other tools. Nimmi already has the chat, the calls, WhatsApp and one memory per person. Email closes
the loop, at about 3 to 8 paise an email.

| Phase | What customers get | Needs |
|---|---|---|
| 0 | Email works on live; sending from the business's own domain; bounces and complaints handled; a safe unsubscribe; email-only leads become contacts; an Email section in the dashboard | - |
| 1 | The owner's two ideas, done well: the welcome email (files, brand, a personal note) and the after-call email (written from the call); a file emailed during a call; meeting emails with "change time"; templates; one Files library for WhatsApp and email | 0 |
| 2 | Two-way email: replies come back; follow-ups stop on a reply; the AI answers or drafts; an Inbox | 0 |
| 3 | Leads from other places by email (portals, forms, IndiaMART's real-time feed): an email at once, a call within minutes | 2 |
| 4 | Journeys: follow-up plans across email, WhatsApp and calls, by lead status, with branches and goals; lead stages | 1, 2 |
| 5 | Broadcasts, properly: segments, consent, scheduling, subject tests, reports | 0 |
| 6 | Tracking, a lead score from engagement, reports, alerts when a lead is hot | 1 |
| 7 | The AI email agent, within limits; Nimmi (the dashboard's agent) runs email for the business | 2, 4 |
| 8 | Connect Gmail or Outlook (send as the team member) and calendars | 2 |
| 9 | Scale: Amazon SES with each customer's reputation kept apart, dedicated IPs, the brand logo in Gmail, CRM sync | as needed |

Each phase ships on its own and is useful by itself. Nothing goes live without the owner's OK (push, Railway, DNS).

## 1. What exists today (read from the code, 1 Nov 2026)

- **Sending** (`backend/notify/email.py`): Resend, else SMTP. Every customer email goes from one Nimmi address
  (`EMAIL_FROM`, default `Nimmi AI <notifications@nimmiai.in>`) under the business's name, with Reply-To set to the
  business's own address. One-click unsubscribe headers (RFC 8058) when a link is passed. Attachments work (used for
  meeting invites).
- **On live, nothing is sent today.** Railway has no `RESEND_API_KEY` (health shows `"email": false`, 31 Oct 2026).
  Team alerts, password resets, invites, billing reminders, meeting emails and automatic emails all fail quietly there.
  Whether `nimmiai.in` is verified in Resend couldn't be checked from here (Resend > Domains shows it).
- **Team alerts** (`notify/events.py`): a new lead, call summaries, "wants a person"; up to 5 addresses; each once.
- **Automatic emails to customers** (`notify/automations.py`, Integrations > Email). There are five triggers, all off
  by default:
  - after a chat (`chat_lead`);
  - after a call (`call_lead`);
  - goal met on a call (`goal_met`);
  - couldn't reach them (`call_missed`);
  - after the team helps in Live chat (`handoff_done`).

  Each is up to 3 emails (now, 1 hour ... 14 days). Placeholders: `{{name}}`, `{{business}}`, `{{assistant}}`,
  `{{email}}`, `{{phone}}`, `{{summary}}`, `{{details}}` and any collected field. The text is plain, inside a simple
  card.
  - Queued as `EmailJob` rows and sent by the scheduler 50 at a time, each once: a NotificationLog claim, so the four
    processes never send twice.
  - Later emails stop when the person unsubscribes, the automation is turned off, a step is removed, or a later call
    reached its goal.
  - Abuse guard: each automation goes to an address once a day at most; 500 automatic emails per workspace per day.
- **History and bulk email** (`routers/email_center.py`): every email with its status; resend or cancel; "never email
  this person". Bulk email goes to people who shared an email in chat or on calls (by source, days, hot only): up to
  2,000 people and 5 sends a day, with a consent tick box and a Reply-To required.
- **Meetings** (`voice/meetings.py`): on WhatsApp and email, the written confirmation with a calendar invite (.ics),
  the day-before reminder and the joining details.
- **Plans**: emails to customers (automations, bulk) and team alerts need Growth (`email_alerts` in `plans.py`).
- **Contacts** (`models.Contact`): one per assistant and phone number, shared by calls and WhatsApp, with an email
  when one was heard. A chat lead with only an email isn't a contact; it lives in the chat's collected details.
- **Unanswered questions** (`KnowledgeGap`): grouped by wording and answered on the Questions page. Only the last
  conversation is kept, not everyone who asked.
- **Files** (`WhatsAppFile`): brochures, price lists, menus, each with "when to send" for the AI. WhatsApp only.

Gaps (each is fixed in a phase below):
1. Live can't send email (above).
2. Nimmi never sees replies. They go straight to the business's mailbox, so the second and third follow-ups still go
   out after someone wrote back "yes, call me".
3. Bounces and spam complaints aren't read. Nimmi keeps emailing dead and complaining addresses. That hurts every
   customer, because they all send from one shared address.
4. No business can send from its own domain.
5. Settings are per workspace, not per assistant: a workspace that runs two businesses sends both under one name, with
   the same texts.
6. The text is filled in when the email is queued. If the chat asks for the email before the name, the email says
   "Hi there", and anything said later is missing. The chat email also goes the moment the address is typed, in the
   middle of the conversation.
7. The unsubscribe link acts on a plain visit. Email security scanners open links, so people can be unsubscribed by
   accident. (The one-click POST is right; the page should ask for a click.)
8. Meeting emails have no Reply-To, so a reply goes to Nimmi's notifications address.
9. No files, images, buttons or brand (logo, colours) in automatic emails, and no preview or test send.
10. Nothing is tracked after sending (delivered, clicked, replied), so there are no reports and no "hot lead" signal.
11. The phone agent can't send anything during a call ("I'll email you the price list").
12. One language per text: nothing follows the person's language (calls and WhatsApp do).

## 2. Market research (Oct to Nov 2026)

### 2.1 Salesforce, the benchmark

- **Agentforce SDR** (the Sales Development agent) works inbound leads on its own, around the clock. It:
  - emails them, answers their questions and books meetings;
  - hands each booked meeting to a seller with a briefing.

  Admins set how often it contacts people, on which channels and when, and its tone. Salesforce's guide asks for an
  email address on the company's own domain, used only by the agent.
  ([announcement](https://www.salesforce.com/news/stories/einstein-sales-agents-announcement),
  [implementation guide](https://www.salesforce.com/en-us/wp-content/uploads/sites/4/documents/guides/Agentforce-for-Sales-Development-Implementation-Guide.pdf))
- **Sales Engagement cadences**: steps of emails, calls and tasks for a seller to follow. Templates and call scripts
  have merge fields that fill in each person's details, and templates can be A/B tested on a step.
  ([Trailhead](https://trailhead.salesforce.com/content/learn/modules/standard-cadences-for-sales-engagement/improve-cadence-strategy-with-advanced-options))
- **Einstein Activity Capture** syncs sellers' emails and meetings into the CRM, so each person's record shows every
  conversation.
  ([Trailhead](https://trailhead.salesforce.com/content/learn/modules/high-velocity-sales/boost-productivity-with-high-velocity-sales))
- **Salesforce Inbox**: send later, open and click tracking, and "insert availability" (the person picks a time from
  the email). About $25 a user a month as an add-on (a third-party figure).
  ([guide](https://nektar.ai/salesforce-inbox-what-it-is-features-pricing-and-limitations/))
- **Account Engagement (Pardot)**: Engagement Studio nurtures leads by their behaviour or on a timetable. A **score**
  measures engagement and a **grade** measures fit; the two together decide when a lead goes to sales.
  ([Trailhead](https://trailhead.salesforce.com/content/learn/modules/pardot-lead-nurturing-lightning/integrate-lead-nurturing-into-your-marketing-strategy),
  [Forvis](https://www.forvis.com/article/2022/12/salesforce-marketing-cloud-account-engagement-lead-scoring-grading))
- **Marketing Cloud Journey Builder** has:
  - decision splits on a person's data (up to 20 paths) and engagement splits (opened, clicked);
  - waits;
  - Einstein Send Time Optimization (each person gets emails at their best hour);
  - Engagement Frequency (how often each person should hear from you).

  ([Trailhead](https://trailhead.salesforce.com/content/learn/modules/journey-builder-campaigns/build-a-journey-campaign))
- **Prices** (from third-party guides; Salesforce's own page wasn't reached):
  - Starter Suite: about $25 a user a month, with simple email marketing and 2,000 marketing emails a month.
  - Agentforce: Flex Credits at $500 per 100,000 credits; a standard action uses 20 credits (about $0.10).

  ([Zeeg](https://zeeg.me/en/blog/post/salesforce-small-business-pricing),
  [eesel](https://www.eesel.ai/blog/agentforce-pricing))

What we take:
- one record per person, with every conversation on it;
- follow-up plans mixing email, calls and tasks that stop when the person replies;
- a score (engagement) and a grade (fit), used together;
- an agent with limits that hands over with a brief;
- a mailbox on the business's own domain;
- each person's best hour, and a cap on how often they hear from the business.

What we leave: several products to buy and connect, an admin to run them, per-user prices, weeks of setup. Nimmi's
customers need ready-made automations that work in minutes, priced per assistant.

### 2.2 HubSpot

- HubSpot has two kinds of follow-up:
  - **sequences**: personal emails from a seller, enrolled by hand, that stop when the person replies or books;
  - **workflows**: automatic nurture, scoring and internal alerts.

  ([Default](https://default.com/post/hubspot-sequences-vs-workflows))
- **Breeze Prospecting Agent** watches for buying signals and writes personal outreach. It costs $1 for each lead it
  recommends outreach for. ([HubSpot](https://www.hubspot.com/products/sales/ai-prospecting-agent))
- What we take: the same split. "Personal" emails are plain and come from a team member's name, as if a person typed
  them; they are for one-to-one follow-up. Designed emails are for updates and offers.

### 2.3 The Indian CRMs

- **Zoho CRM**: free for up to 3 users; Professional is about ₹1,400 a user a month (annual, plus 18% GST); workflow
  rules send automatic emails. (Partner guides, e.g.
  [Cloudfy](https://cloudfysystems.com/blog/zoho-crm-pricing-india-2026).)
- **Freshsales** (founded in Chennai): $9 / $39 / $59 a user a month. Sequences and the stronger Freddy AI come from
  Pro, with some AI as paid add-ons (sources disagree). ([LeadHaste](https://leadhaste.com/blog/freshsales-pricing-2026))
- **LeadSquared** (Bengaluru):
  - autoresponders, and drips by time or by behaviour;
  - visual workflows with email, SMS and WhatsApp nudges;
  - strong in education and lending;
  - rated 4.3 of 5 on Capterra India (167 reviews).

  ([LeadSquared](https://www.leadsquared.com/lead-nurturing/),
  [Capterra](https://www.capterra.in/directory/31563/lead-nurturing/software))
- What we take: Indian businesses pay per user for CRMs that don't speak to callers. LeadSquared shows that "lead stage
  plus automatic nudges on every channel" sells in India. Nimmi already sends leads to LeadSquared; email events will
  go there too (phase 6).

### 2.4 Chat and voice AI

- **Intercom Fin** answers chat and email on its own, for about $0.99 per resolved conversation (third-party figures).
  ([Gleap](https://www.gleap.io/blog/intercom-fin-ai-pricing-2026))
- **Retell** (the voice platform Nimmi's call prices compare with) can send an SMS after a call, written by the model
  from the transcript. A follow-up email has to go through HubSpot or Zapier.
  ([Retell docs](https://docs.retellai.com/integrations/agent-workflow.md),
  [HubSpot guide](https://docs.retellai.com/integrations/hubspot))
- What we take: voice AI platforms leave the email to other tools. Here the same product that took the call sends the
  email, written from the call, with the files promised on it and the meeting invite. That is a real difference.

### 2.5 AI sales agents (11x, Artisan): the lessons

- Buyers who used them as full replacements for sales reps had mostly moved to a mix by early 2026: the AI drafts,
  people send. Fully automatic sending with little review is where wrong facts, an off-brand voice and spam-folder
  problems show up. The sources are mostly vendor blogs, so the direction matters more than the figures.
  ([Naoma](https://naoma.ai/articles/ai-sdr-dying-2026), [DevCommX](https://www.devcommx.com/blogs/artisan-vs-11x-vs-aisdr),
  [Autobound](https://autobound.ai/blog/ai-sdr-tools-buyers-guide))
- What we take:
  - Nimmi emails only people who contacted the business, and its customers: no cold email, no bought lists.
  - What the AI writes is checked against the knowledge.
  - Nurture starts in "review first".
  - The confirmations people expect (welcome, call recap, meeting) can go on their own.

### 2.6 Indian buyers, channels and cost

- Mobile users in India most prefer WhatsApp for hearing from businesses (45%), with email close behind (41%), then
  SMS (35%), calls (33%) and Instagram (29%). This is an MEF survey of consumers; its date is unclear.
  ([MEF](https://mobileecosystemforum.com/mef_data_post/whatsapp-in-india))
- Email stays the channel for documents, quotes and proposals, and for buyers whose companies don't allow WhatsApp for
  work. Several sources say so; none is a rigorous Indian B2B survey.
- **Cost of an email:** about $0.0004 on Resend's Pro plan, which is 3 to 4 paise at the ₹85 a dollar used in
  `voice/catalog.py`.
- **Cost of WhatsApp:**
  - replies inside its 24-hour window are free for the first 1,000 a number a month, then about ₹0.115 each;
  - marketing templates cost about ₹0.86.

  Outside the window, a follow-up by email costs about 25 times less.
- What we take: WhatsApp for short nudges inside its window; email for the substance (recaps, files, quotes,
  newsletters) and for everything after the window closes. Both run from one plan per lead.

### 2.7 The rules that decide whether email arrives

- **Gmail** (rules since Feb 2024; enforcement stepped up in Nov 2025, with temporary and permanent rejections): anyone
  sending 5,000 or more emails a day to Gmail users is a bulk sender, permanently. Bulk senders need:
  - SPF, DKIM and DMARC (at least `p=none`), aligned with the From domain;
  - one-click unsubscribe on marketing and subscribed emails (receipts and confirmations are exempt);
  - spam complaints under 0.3% (aim for under 0.1%).

  ([Red Sift](https://redsift.com/blog/gmails-enforcement-ramps-up-what-bulk-senders-need-to-know),
  [Google](https://support.google.com/mail/answer/15263077?hl=en))
- **Outlook.com** (from 5 May 2025, for 5,000 or more a day): SPF, DKIM and aligned DMARC. Mail that fails goes to junk
  first, and will be rejected later.
  ([Microsoft](https://techcommunity.microsoft.com/blog/outlook/strengthening-email-ecosystem-outlook%E2%80%99s-new-requirements-for-high%E2%80%90volume-senders/4399730))
- Nimmi as a whole passes 5,000 a day long before any one customer does, so every Nimmi sender is set up this way from
  the start.
- A business with only a `@gmail.com` address can't send as that address through Nimmi: only domains whose DNS you
  control can be verified. It sends from Nimmi's sending domain under its own name, with replies going to its Gmail,
  or it connects its Gmail (phase 8).
- **India's DPDP Rules:** notified 13 Nov 2025. Consent managers start on 13 Nov 2026. The core duties (notice,
  consent, rights, security, breach reporting) apply from 13 May 2027.
  ([Wikipedia](https://en.wikipedia.org/wiki/Digital_Personal_Data_Protection_Rules,_2025),
  [Legismith](https://legismith.com/dpdp-rules-2025-timeline/))

  Our reading for the design, to confirm with a lawyer:
  - Emails about the person's own enquiry (the welcome, the call recap, their meeting) serve the "specified purpose"
    they gave their email for (section 7(a) of the DPDP Act).
  - Newsletters, offers and nurture of cold leads need consent that is clear, specific, and as easy to withdraw as to
    give.
  - The business decides what to send (the data fiduciary); Nimmi processes for it and keeps the records: which notice
    was shown, consent given or withdrawn, when and where.

### 2.8 Measuring honestly

- **Opens can't be trusted.** Apple Mail loads the tracking image for every email, read or not, and security scanners
  click links too. Replies are the most reliable signal; clicks come next, once scanner clicks are filtered out.
  ([GMass](https://www.gmass.co/blog/apple-mail-privacy-protection/),
  [CMSWire](https://www.cmswire.com/digital-marketing/did-apple-and-gmail-break-email-measurement-or-just-expose-it/))
- **Speed matters.** In the 2007 lead response study (InsideSales.com and James Oldroyd, often called "the MIT
  study"), a first attempt within 5 minutes instead of 30 made contact 100 times more likely, and qualification 21
  times. A later Harvard Business Review analysis found that firms responding within an hour were nearly 7 times more
  likely to qualify the lead. Both are vendor data, not peer reviewed, but they agree.
  ([Callingly](https://callingly.com/blog/state-of-speed-to-lead),
  [study PDF](https://www.mortech.com/hs-fs/hub/25649/file-13535879-pdf/docs/mit_study.pdf))
- What we take: reports lead with replies, meetings and clicks; opens are shown only as an estimate and never drive
  decisions; the first email goes out within minutes.

### 2.9 How to send: the options

- **Resend** is what Nimmi uses. From its own pages, read 1 Nov 2026:
  - **Plans:** Free 3,000 emails a month (100 a day). Pro $20 for 50,000 or $35 for 100,000, then $0.90 per 1,000.
    Scale from $90 for 100,000 up to $1,150 for 2.5 million.
  - **Domains:** Free 3, Pro 10, Scale 1,000 (+100 for $20 a month).
  - **Other limits:** logs are kept 30 days. A dedicated IP is $30 a month, on Scale only, above 3,000 emails a day.
    Resend's own broadcasts are priced separately, by contacts ($40 a month for 5,000 on Pro).
  - **Receiving:** any address at a domain whose MX record points to Resend, or a `*.resend.app` address. A webhook
    brings the details; the body and attachments are then fetched by API (their download links last an hour). Each
    received email counts towards the monthly emails.
  - **API:** 10 requests a second per team (can be raised); batches of up to 100 emails a request; idempotency keys
    kept 24 hours; scheduled sending.
  - **Many customers:** one domain per customer through the Domains API, a sending-only API key for each domain, and
    tags to route events. Resend recommends a subdomain for sending, and a warm-up for each new domain.
  - **Events:** sent, delivered, delivery delayed, bounced, complained, opened, clicked, failed, suppressed, received,
    scheduled. They are signed by Svix and delivered at least once, so they must be deduplicated.

  ([pricing](https://resend.com/pricing), [receiving](https://resend.com/docs/dashboard/receiving/introduction),
  [API](https://resend.com/docs/api-reference/introduction),
  [multi-tenant](https://resend.com/docs/knowledge-base/setting-up-resend-for-multi-tenants),
  [events](https://resend.com/docs/dashboard/webhooks/event-types),
  [idempotency](https://resend.com/docs/dashboard/emails/idempotency-keys))
- **Amazon SES:**
  - $0.10 per 1,000 emails sent, plus $0.12 a GB of attachments; receiving $0.10 per 1,000;
  - "tenants" keep each customer's reputation apart: 1,000 are included per region, then $0.005 a month each.

  At volume it costs a quarter of Resend or less, but it is more work to run: phase 9.
  ([AWS](https://aws.amazon.com/ses/pricing/))
- **The business's own mailbox (Gmail, Outlook):**
  - Sending only (`gmail.send`) is a "sensitive" scope: it needs Google's app verification, but no yearly audit.
  - Reading mail (`gmail.readonly`, `gmail.modify`) is "restricted": it needs a yearly CASA security assessment when
    the data reaches our servers. Quotes vary from hundreds to tens of thousands of dollars.
  - Google Workspace allows 2,000 emails a day per person; a free Gmail account about 500.

  ([Nylas](https://developer.nylas.com/docs/cookbook/use-cases/build/google-oauth-scopes/),
  [DeepStrike](https://deepstrike.io/blog/google-casa-security-assessment-2025),
  [Google](https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace))
- **Choice:**
  - Resend now: one account, a domain per customer, and receiving for replies.
  - SES only when volume makes it worth it.
  - Mailbox connection later, send-only. Replies still come through Nimmi (section 5.4), so no restricted scope and no
    yearly audit.

### 2.10 Lead portals

- IndiaMART's Lead Manager, for paid sellers, can push each lead to a CRM the moment it arrives (the Push API). Its
  older Pull API fetches leads every few hours; it is being phased out for Zoho, and a Pull key expires after 7 idle
  days.
  ([Pull API](https://help.indiamart.com/knowledge-base/lms-crm-integration-v2),
  [Push API](https://help.indiamart.com/knowledge-base/integrating-indiamarts-lead-manager-with-zoho-crm-in-real-time))
- JustDial, the property portals and website form tools email each lead to the business, and Nimmi can read those
  emails (phase 3). The portals weren't researched one by one: the AI reads any format.

### 2.11 Where Nimmi stands

Today the pieces a business needs for its leads are spread across tools:
- a CRM and email tool (Salesforce, HubSpot, Zoho, LeadSquared);
- a WhatsApp tool;
- a voice AI platform (Retell sends an SMS; its email goes through HubSpot or Zapier).

Nimmi already has the website chat, phone calls and WhatsApp, with one memory per person. This plan adds three things:
- emails written from those conversations;
- replies that come back to the same memory;
- follow-ups across all three channels.

With them, Nimmi becomes the one place a small business needs for its leads, priced per assistant, not per user.

## 3. Principles

1. **Only people who reached out.** Nimmi emails people who contacted the business (chat, call, WhatsApp, a form, a
   portal) and its customers. No bought lists and no cold email; an import needs the business to confirm consent.
2. **Useful every time.** Each email says what they asked, what was agreed and what happens next, and brings the
   files. No filler.
3. **From the business.** Its name, a team member's name and signature, its own domain once connected, its logo and
   colours.
4. **Facts only.** The AI writes from the business's knowledge and from what was said. A price, date or number that
   isn't in either is left out (the same check flows use). It never promises what the call didn't agree.
5. **Stop when they answer.** A reply, a booking, an unsubscribe, a complaint or "do not call" stops every follow-up on
   every channel at once.
6. **One memory.** Emails sit on the same contact as calls, chats and WhatsApp. The next call knows what was emailed
   and what they replied.
7. **Their language.** An email follows the language of the person's last message or call (Tamil, Hindi, Tanglish in
   English letters, and so on), as calls and WhatsApp already do.
8. **Respect.** A cap on how often one person hears from the business across all emails, quiet hours, consent for
   marketing, one-click unsubscribe, honest numbers.
9. **Safe defaults.** The confirmations people expect (welcome, call recap, meeting) can go on their own. Anything the
   AI writes freely for nurture starts in "review first", and the business can move each one to automatic.
10. **Reliable.** Claims in the database and idempotency keys, so four processes and restarts never send twice or lose
    an email; every failure has a reason in plain words.

## 4. How it works: one lead, start to end

Example: Sunrise Homes, a builder in Chennai, on Growth with its own domain connected. Priya runs sales.

1. **10:02.** Karthi asks on sunrisehomes.in about 2BHK flats in Anna Nagar, and gives his name, email and phone.
2. **10:05.** The chat has been quiet for 2 minutes. An email arrives from "Priya at Sunrise Homes"
   (priya@sunrisehomes.in): "Hi Karthi, thanks for asking about our 2BHK homes in Anna Nagar..."
   - Attached: the brochure and the floor plans.
   - Buttons: "Book a site visit" (free times from Schedule), "Call me now" and WhatsApp.
   - The note about Anna Nagar was written by the AI from his chat; the rest is Priya's template.
3. **10:06.** He taps "Call me now".
   - The assistant calls him within a minute (Pro, within calling hours).
   - It answers his questions about loans from the knowledge and books a site visit for Saturday 11 am.
   - On the call he asks for the price list: "I've just emailed it to you." It arrives while they talk.
4. **10:14.** After the call, a recap email: the two answers he asked for, and the site visit with a calendar invite
   and a "Change time" link. The price list isn't sent again.
5. **Friday 11 am.** A reminder by WhatsApp and email, with the map link.
6. **Saturday.** Priya marks the visit attended. On Monday a thank-you email goes with the quotation she uploaded: the
   AI drafted it from her note, and she approved it in one click.
7. **No reply for 3 days.** The journey sends a WhatsApp nudge; on day 7 an email about the bank partners; on day 14,
   "Shall I close your enquiry?"
8. **Karthi replies:** "Still interested. Call me next Tuesday evening." Nimmi books a call-back for Tuesday 6 pm,
   stops the journey and tells Priya. His contact shows every step, and the lead score says hot: he replied and
   downloaded the price list twice.

Another lead the same night: at 9:40 pm IndiaMART sends a lead (name, phone, email, "need 2BHK under ₹80 lakh").
Nimmi creates the contact and emails at once ("we'll call you tomorrow morning"). It calls at 10 am, when calling
hours start.

## 5. Everything it does (with the phase)

### 5.1 Sending and deliverability
- **Sending from** (phase 0):
  - Nimmi's own sending domain for customer emails, `mail.nimmiai.in`. Nimmi's own emails, such as password resets,
    stay on `nimmiai.in`, away from customers' mail.
  - Or the business's own domain, verified from the dashboard: the DNS records to add, with steps for GoDaddy,
    Hostinger, Cloudflare and others, then checked every few minutes until verified.
  - Each assistant can have its own From name and address (gap 5).
- **A separate subdomain for marketing** (`news.`), so offers never spoil confirmations (phase 5).
- **Bounces, complaints and suppressions** (phase 0):
  - A complaint stops that address for that business.
  - A hard bounce stops it for every business: a dead address is dead for everyone.
  - Follow-ups are cancelled, and it shows on the contact.
- **Address check before the first email** (phase 0): the format; whether the domain receives mail (MX); throwaway
  domains; typos ("gmial.com": the chat asks "Did you mean gmail.com?").
- **Warm-up and limits** (phase 0):
  - A new domain starts with a small daily limit that grows.
  - Each workspace has limits by plan.
  - Complaints are watched per workspace: above 0.3% its bulk sends pause and the owner is told.
- **Checks before a template is saved:** link safety, all-caps subjects, image-only emails, and a size under 100 KB
  (Gmail cuts longer emails). A plain-text part is always included.
- **One-click unsubscribe** (exists). Phase 0 makes the page ask for a click and adds a preferences page with three
  choices: "only about my enquiry", "offers and news too", "nothing".

### 5.2 Consent and privacy (phases 0 and 5)
- **Where consent is asked:**
  - The chat's email question gets a one-line notice the business can edit ("We'll email you about your enquiry.") and
    an optional tick box for offers and news.
  - On calls the agent asks "Can we email you the details?"
  - Forms and imports record their own consent.
- **Records,** per contact and channel: the purpose (their enquiry, or marketing), the exact words shown, where (chat,
  call, form, import, team) and when. Consent is withdrawn when they unsubscribe or ask on any channel; "stop emailing
  me" on WhatsApp counts.
- **Who gets what:** broadcasts and cold-lead nurture go only to people with marketing consent. Emails about their
  enquiry go to everyone who gave their email for it (section 2.7).
- **Keeping data:** email text is kept for a period the business picks (12 months by default); the record that an
  email was sent stays. Compliance > Erase removes the person's emails too.

### 5.3 Automatic emails (the triggers)

**Chat:**
- **Welcome email** (phase 1):
  - Goes when the chat goes quiet (2 minutes after their last message, or when they close the chat), written at that
    moment with everything they said. Set per assistant.
  - A template plus an optional AI note from the chat.
  - Files, either fixed or picked by the AI by "when to send".
  - Buttons: book a time, call me, WhatsApp, the website.
- **"Email me this chat"** in the widget (phase 1).
- **A visitor asked for a person and nobody answered:** "Sorry we missed you", with what happens next (phase 1).
- **Left halfway** (gave the email, didn't finish booking): a reminder with a link to continue (phase 4).
- **The answer to a question the AI couldn't answer** (phase 4): when the team writes the answer on Questions, it can
  be sent to everyone who asked it and left an email (the team ticks who). This needs a record of who asked, since
  `KnowledgeGap` keeps only the last conversation today.

**Calls:**
- **After-call email** (phase 1), written from the call:
  - thanks and a short recap;
  - answers to the questions they asked, from the knowledge. What the knowledge doesn't cover goes to Questions, and
    the email says the team will reply;
  - the next step with its date (the meeting, the call-back, the team's to-do);
  - the files promised on the call, and how to reach the business.

  It has separate settings for incoming and outgoing calls (like the agent's other settings), and three modes:
  automatic, review first (the team approves in Email > Drafts), or off. It is written in the person's language.
- **During the call** (phase 1): a new tool, `send_email`, so the agent can say "I've emailed you the price list."
  - It goes to the address on file. The agent never reads it out; it only knows there is one.
  - Or to an address they give on the call, spelt back letter by letter.
  - With WhatsApp connected, a message with a link to type the address in instead.
- **Other call emails:** couldn't reach them (exists); voicemail left (phase 1); call-back booked ("We'll call you at
  4 pm", with "change time") (phase 1).

**Meetings** (phase 1):
- the confirmation with the invite, and "Change time" and "Cancel" links (a page with free times; bookings go through
  `meetings.py`);
- the day-before reminder and the joining details;
- afterwards, a thank-you if they attended, or "sorry we missed you" with a rebook link if they missed it;
- the business's Reply-To (gap 8).

**WhatsApp:**
- A WhatsApp chat that collects an email gets the same welcome, if it's on (phase 1).
- When the 24-hour window closes with something still to send, it goes by email instead of a paid template (phase 4).

**Customers and the rest of the relationship** (phase 4):
- When a contact is marked customer: a welcome, how to get started, a review request (their Google review link) and a
  referral ask.
- Dates the business keeps (service due, renewal, birthday) get reminders.
- A feedback question after a call, chat or meeting (good or bad, plus a comment).

**The team** (phases 1 and 6): today's alerts; a daily summary for the owner (new and hot leads, meetings today,
replies waiting, questions to answer); a weekly report.

### 5.4 Replies: two-way email (phase 2)

- **Where replies go.** Every email's Reply-To is a Nimmi address for that conversation (`r-<code>@reply.nimmiai.in`,
  later the business's own `reply.` subdomain). The From still shows the business.
  - Replies come back to Nimmi and go on the contact.
  - A copy is forwarded to the business's own mailbox, as today, so nothing changes for them.
- **Answering from Gmail.** The forwarded copy's Reply-To is the same Nimmi address. So when the business answers from
  Gmail, the answer goes through Nimmi to the lead, sent as the business, and Nimmi sees both sides. Only the team's own
  addresses can do this, checked with SPF and DKIM.
- **On every reply**, follow-ups stop and the team is told. The AI reads the reply and acts on what it is:
  - a question: answers it from the knowledge, or drafts an answer;
  - "call me": books a call-back at the time they said, through the Schedule tools;
  - "let's meet": sends free times, or books one;
  - not interested: updates the lead status;
  - stop emailing: unsubscribes them;
  - out of office or an auto-reply: no answer; tries again after their return date;
  - someone else: notes it.
- **Each assistant chooses who answers:** the AI answers; the AI drafts and the team sends; or the team only.
  - The AI never sends more than a few answers per conversation a day.
  - It never answers auto-replies, no-reply addresses or mail servers, so no loops.
- **Email > Inbox:** conversations by contact; assign to a team member; notes; templates; "Write with AI"; files; and
  the whole timeline (chat, calls, WhatsApp) beside it.

### 5.5 Journeys and lead stages (phase 4)

- **A journey** starts from a trigger and runs steps until it ends.
  - Triggers:
    - a new lead from chat, a call, WhatsApp, a form or a portal;
    - a lead status change;
    - a meeting booked, attended or missed;
    - a contact marked customer;
    - a date.
  - Steps:
    - send an email (template or AI);
    - send a WhatsApp message;
    - call (a Schedule follow-up call);
    - wait (for a time, until a weekday and hour, or until something happens);
    - branch (replied, clicked, downloaded, booked, status, a collected detail);
    - update the contact (status, tag, owner);
    - tell the team, or make a to-do.
  - A goal (booked, customer, replied) ends it. An unsubscribe, a complaint or "do not call" ends it at once.
- **Ready-made journeys:** a new website lead; after a call with an interested person; couldn't reach them; meeting
  missed; cold lead (needs marketing consent); new customer; service due. Each opens filled in, with emails written
  from the business's knowledge.
- **One cap for all journeys:** at most one email a day and three a week to one person (the business can change it);
  quiet hours; each person's usual hour (Schedule already calls at about the hour they last picked up).
- **One place:** the existing 3-step automations and Schedule's follow-up calls by lead status become journeys (their
  settings move over), so there's one place to see what each lead will get.
- **Lead stages,** beside the status (hot, warm, cold): new, contacted, interested, meeting, customer, lost. Each lead
  has an owner (round-robin is optional) and tags; a simple board shows them.
- **Built as a list of steps,** not a free canvas, so it works on a phone. "Write with AI" turns "email them now,
  WhatsApp after 2 hours if no reply, call the next morning" into steps.

### 5.6 Templates, brand and files (phase 1)

- **Templates** per assistant, by kind (welcome, after call, meeting, follow-up, broadcast), in several languages.
  Ready-made sets per industry (real estate, clinics, schools and coaching, salons, insurance, travel), in English,
  Tamil and Hindi first.
- **Blocks:** heading, text, image, button, files, divider, signature, social links.
  - Placeholders have a fallback: `{{name|there}}`.
  - A block can show only when something is known ("if they booked a meeting").
  - Phone and desktop preview, dark mode, a test send to yourself, and a preview with a real recent conversation.
- **The brand kit** comes from the assistant's Design (logo, colour, font) and can be edited.
- **Personal emails:** plain text with a signature, as if a person typed it. For one-to-one follow-ups, where designed
  emails look like ads.
- **The AI note:** a short paragraph written for each person from their conversation, inside the template. The
  business sets what it may talk about.
- **Files:** one library for WhatsApp and email (today's WhatsApp > Files, renamed "Files" and opened to email). Small
  files are attached. Large ones (over a few MB) go as a download link, which also tells the business who downloaded.
- **Signatures** per team member.

### 5.7 Broadcasts (phase 5)

- **Segments,** saved by assistant, status, stage, source, tags, interest, language, last activity or engagement.
  Only people with marketing consent are included, and never the unsubscribed, bounced or complained.
- **Sending:** at a set time, or at each person's usual hour (optional). Two subjects can be tested on 20% of the list,
  with the better one (by clicks and replies) sent to the rest. A test send and spam checks before sending.
- **Sent slowly** from the marketing subdomain. Reports: delivered, clicked, replied, unsubscribed, complaints,
  bounces. A spike in complaints pauses the send.
- **Event invitations** with RSVP buttons (yes, no, maybe) that update the contact and send reminders.
- **Imports** (CSV): the consent source is required.

### 5.8 Tracking, score and reports (phase 1 for links, phase 6 for the rest)

- **Events per email:** sent, delivered, bounced, complained, clicked, replied, unsubscribed, file downloaded,
  meeting booked from it. Opens are shown as an estimate only.
- **Links** go through Nimmi's link address (later a domain of the business's own, e.g. `links.sunrisehomes.in`).
  Clicks from security scanners are filtered out: those within seconds of delivery, and known scanners.
- **Lead score:** today's chat and call score, plus email engagement. A reply counts most, then a click on booking, a
  click on pricing, a download; opens count for nothing. A "Hot now" list.
- **Alerts:** "Karthi just downloaded the price list", to the team (dashboard and email). Optionally (Pro), a call
  within 5 minutes when someone taps "Call me", or opens the booking page without booking.
- **Reports:**
  - each automation, journey, template and broadcast;
  - the funnel: leads, emailed, replied or clicked, meetings, customers;
  - each team member: replies, time to reply;
  - deliverability: bounce and complaint rates, domain checks, steps for Gmail's Postmaster Tools.
- **Events to the business's webhook and LeadSquared** (Pro integrations): email sent, replied, clicked, bounced,
  unsubscribed.

### 5.9 AI (phases 1, 2 and 7)

- **Writing:** the welcome note, the after-call email, answers to replies, follow-ups, subject lines, translations.
  - Grounded in the knowledge and the conversation.
  - A fast model checks each email before it goes (invented numbers, promises, the right files and dates) and fixes
    it or holds it.
- **Counting:** an AI-written email counts as one AI reply of the assistant's plan (the same counter as chat and
  WhatsApp). Template emails don't.
- **The email agent** (phase 7) handles replies and nurture within the journey's limits:
  - picks the next best message;
  - answers objections from the knowledge;
  - books;
  - hands hot leads to the team with a short brief: what they want, what they were told, what's next;
  - sends a daily digest of what it did.

  Three levels: drafts only; a morning approval queue; automatic within limits.
- **Nimmi, the dashboard's agent** (phase 7): "set up a welcome email with our brochure", "send the Diwali offer to
  warm leads who asked about 2BHK", "who replied this week?". It gets read, change (with undo) and confirm tools, as in
  NIMMI_AGENT_PLAN.md.

### 5.10 Leads from other places (phase 3)

- **A lead address per assistant** (`leads-<code>@in.nimmiai.in`). The business forwards IndiaMART, JustDial, 99acres,
  MagicBricks, Sulekha or website-form emails there. A Gmail filter can do it automatically; Gmail's confirmation code
  for the forwarding shows in Nimmi's dashboard, so they can finish the setup.
- **The AI reads any format:** name, phone, email, what they want, budget, place, the portal.
- **Then:**
  - a contact is made (or merged) and the source recorded;
  - the "new lead" journey starts: an email at once if there's an address, and a call within minutes in calling
    hours (Pro);
  - a WhatsApp message only if WhatsApp's rules allow it (a portal lead hasn't opted in to WhatsApp).
- **IndiaMART's Push API** straight to Nimmi, for paid IndiaMART sellers: real time, no forwarding.
- **A form webhook** for any website builder (and the WordPress plugin's forms later).

### 5.11 The team
- Each lead has an owner, with assignment rules, and notifications go to that owner. Replies from Nimmi go in the team
  member's name, with their signature.
- Roles as today: the owner and admins set up domains and automations; agents answer in the Inbox.

### 5.12 Connections (phases 8 and 9)
- **Gmail and Outlook:** one-to-one emails sent from the person's own mailbox (Gmail `gmail.send`; Outlook through
  Microsoft Graph Mail.Send). Replies still come through Nimmi's reply address and are forwarded, so no read access is
  needed.
- **Calendars:** Google Calendar and Outlook free/busy for meeting times, and real calendar events with a video link.
  Cal.com already works through functions.
- **CRM sync** of email activity: LeadSquared (which already gets leads), then Zoho, HubSpot and Salesforce (phase 9).
- **Later options:** Razorpay payment links in emails (a booking fee); quotes with "Accept" buttons; documents
  collected by reply.

## 6. Building blocks

### 6.1 Modules

A new `backend/mail/` package, like `voice/` and `whatsapp/`:
- `send.py`: the provider (Resend now, SES later). It replaces the sending part of `notify/email.py`, which stays for
  Nimmi's own emails.
  - one email, or batches of 100;
  - an idempotency key per email (the job id);
  - the domain's own sending key, and tags (workspace, assistant, job);
  - clear reasons for failures.
- `domains.py`:
  - adds a domain through Resend's Domains API, and gives the DNS records to show;
  - checks until the domain is verified;
  - makes the sending-only key (sealed with secretbox), and sets warm-up limits.
- `render.py`:
  - blocks to email-safe HTML (tables, inline styles) and plain text;
  - the brand kit, placeholders with fallbacks, size and content checks.

  Our own small renderer for a fixed set of blocks, so the backend needs no JavaScript build. A drag-and-drop editor
  such as Easy Email (MJML-based, open-source core) comes only if customers ask for one.
- `compose.py`: the AI emails (welcome note, after call, answers to replies, follow-ups):
  - the prompt with the knowledge and the conversation;
  - the number check, and the review by a fast model;
  - the language.
- `events.py`: Resend's webhook, with the Svix signature checked and events deduplicated on their id. It handles
  delivered, bounced, complained, clicked, suppressed and failed; keeps the suppressions; updates contacts.
- `inbound.py`: received emails:
  - fetches the body and attachments;
  - finds the conversation (by the reply address, then In-Reply-To and References, then the sender);
  - cuts the quoted part;
  - detects auto-replies (the Auto-Submitted, X-Autoreply and Precedence headers, out-of-office words);
  - classifies the reply and acts on it;
  - forwards a copy, and relays the team's answers.
- `consent.py` and `suppress.py`: consent records; unsubscribes, bounces and complaints.
- `links.py`: tracked links, file download links, and the signed links for "change time", "call me", "unsubscribe" and
  preferences.
- `journeys.py` (phase 4); `intake.py` (phase 3: lead addresses, portal emails, IndiaMART Push, the form webhook).
- `api.py` (`/api/email/...`) and `public.py`: the pages people open from an email (unsubscribe and preferences,
  change a meeting, call me, downloads, link redirects).

Changes elsewhere:
- `notify/automations.py` and `routers/email_center.py` move into `mail/`; the old settings are carried over.
- `voice/functions.py` reserves `send_email`, and `CallTools` gets it.
- `schedule.after_call` calls the after-call email.
- `meetings._to_person` uses the templates and links.
- `routers/chat.py` and `whatsapp/inbound.py` start the welcome timer.
- `voice/scheduler.py` runs the mail queue, the domain checks and journeys.

Dashboard:
- A new Email section, like Voice and WhatsApp (`app/dashboard/email/`): Overview, Inbox, Automations, Journeys,
  Broadcasts, Templates, Files, Reports, Settings.
- `components/email/`: template editor, preview, domain setup, inbox, journey steps.
- The builder's Leads tab links to that assistant's welcome email; the agent page links to its after-call email for
  each direction.
- Contacts becomes one list for all channels.

### 6.2 Tables

New tables are safe; new nullable columns are added at startup.

New:
- `email_settings`: one row per assistant (and a workspace default): sender, reply handling, brand kit, footer,
  signature defaults, consent wording, limits.
- `email_domains`: the workspace's domains: name, purpose (mail, news, reply), Resend id, status, DNS records, the
  sealed sending key, warm-up stage, when it was checked and verified.
- `email_templates`: kind, language, subject, preheader, blocks, AI note settings, files, version, who changed it.
- `email_events`: the provider's events (deduplicated), linked to the email.
- `email_threads` and `email_inbound`: conversations and received emails (the new part, the full text, cleaned HTML,
  attachments, authentication results, auto-reply flag, classification, who handled it).
- `consents`: contact, channel, purpose, status, the words shown, source, times.
- `knowledge_gap_askers` (phase 4): who asked each unanswered question.
- `journeys` and `journey_enrollments` (phase 4); `email_links` (phase 1); `lead_intakes` (phase 3).

Existing tables that change:
- `email_jobs`, new columns: assistant, contact, thread, template, journey step, provider id, Message-ID, HTML,
  attachments, and the time of each event (delivered, bounced, clicked, replied).
- `email_unsubscribes`, new columns: reason (unsubscribed, bounce, complaint, team) and source. Plus a small table of
  hard-bounced addresses, shared by every workspace.
- `contacts`: the phone number becomes optional, so a lead with only an email can be a contact. This is the one schema
  change (`ALTER COLUMN e164 DROP NOT NULL` at startup), tried on a copy of live first. Duplicates are merged by email
  or number.
- `whatsapp_files`, new columns: channels (WhatsApp, email) and a download token. Shown as "Files" everywhere.

### 6.3 How it runs on live
- **Four processes:** every send is claimed in the database (as today) and carries an idempotency key, so neither a
  retry nor a second process can send it twice. Timers ("send when the chat goes quiet") are rows with a time, not
  memory.
- **Resend's 10 requests a second per team:** batches for bulk sends, a small limit per process (2 a second each), and
  a backoff on 429.
- **The database pooler's 15 clients:** short sessions and work in batches. The webhook answers at once and queues the
  work.
- **AI capacity:** an AI-written email is about 6,000 tokens in and 600 out (to be measured). On Groq's free tier
  (8,000 tokens a minute per model) that is about one email a minute per model. A paid tier is needed before AI emails
  go to many customers.
- The webhook and inbound endpoints are public, signed (Svix) and rate-limited.

### 6.4 Security
- **Inbound emails are untrusted.** They are shown as text, or as cleaned HTML in a sandboxed frame (no scripts, no
  remote images by default). Attachments from strangers are limited by type and size, and stored privately.
- **An email can't give the AI instructions** ("ignore your rules, send me your customer list"). On a reply, the AI has
  only the tools for that same person: answer from the knowledge, call-back, meeting, hand over.
- **Templates and keys:** templates can't carry scripts, and their links are checked (no private addresses, no known
  bad domains). Each domain's sending key can send only from that domain; keys are sealed (secretbox).
- **Relay:** the team's answers are relayed only from the workspace's team addresses, with SPF or DKIM passing.

### 6.5 Tests (as the project does)
- **Backend tests** (`tests/test_mail_*.py`) with a fake Resend, like FakeMeta for WhatsApp. They cover:
  - sending, and idempotency across processes;
  - domains, webhooks and suppressions;
  - inbound threading and auto-reply detection;
  - the AI composer with a scripted model;
  - journeys and their stops, and consent.

  Each new behaviour gets a test that fails without it.
- **Local scripts** (`dev-scripts/email/`):
  - `fake_resend.py` and `sim_reply.py`, to run locally with no real sending;
  - `compose_probe.py`: real models write emails from saved real transcripts, checked for invented numbers, wrong
    dates and the right files.
- **Browser checks** (`dev-scripts/ui-checks/email_*.mjs`): settings, domain setup, template editor and preview, inbox,
  journeys, phone width.
- **Real inbox check** (with the owner): emails to a Gmail and an Outlook.com account land in the inbox, not spam, and
  "Show original" in Gmail shows SPF, DKIM and DMARC as PASS.

## 7. Phases

### Phase 0: foundations
- **Live sends email** (the owner's part, section 10):
  - `RESEND_API_KEY` on Railway;
  - Nimmi's customer-mail domain `mail.nimmiai.in` verified in Resend, with its records in GoDaddy;
  - a DMARC record for nimmiai.in (`p=none` first, reports to a mailbox the owner reads).
- **The Resend webhook** (`/api/email/webhooks/resend`), for bounces, complaints, suppressions and failures: the
  addresses are stopped, follow-ups cancelled, and both show in History and on the contact.
- **Sending fixes:**
  - an idempotency key on every send;
  - the text filled in at send time (gap 6);
  - meeting emails get the business's Reply-To (gap 8).
- **Unsubscribe:** the page asks for a click (the POST stays one-click), and there is a preferences page.
- **Address checks:** format, MX, throwaway domains, and a typo suggestion in the widget.
- **The business's own domain:** Settings > Sending domain shows the records to add, with copy buttons and steps for
  the common DNS providers, then checks automatically and warms the domain up. Each assistant gets its own sender name,
  address and Reply-To (gap 5).
- **Contacts:** email-only leads become contacts, and Contacts shows emails as well.
- **The Email section** in the dashboard: Overview, History (moved), Settings (moved, plus the new parts).
  Integrations > Email links there.
- **Done when:**
  - a test email from live lands in the owner's Gmail inbox with SPF, DKIM and DMARC PASS;
  - Resend's test addresses (bounced@resend.dev, complained@resend.dev) end up suppressed, with their follow-ups
    cancelled;
  - a test domain verifies from the dashboard;
  - a link scanner opening the unsubscribe link changes nothing;
  - the test suite and the browser checks pass.

### Phase 1: the owner's two ideas, done well
- **Welcome email:** per assistant, sent after the chat goes quiet. A template, the AI note, files and buttons, in
  their language, from the business. Preview with a real chat; test send. On WhatsApp chats too.
- **After-call email:** written from the call (recap, answers, next step, promised files, meeting or call-back).
  - Per direction: automatic, review first, or off.
  - Email > Drafts for the review.
  - Questions it couldn't answer go to Questions.
- **`send_email` on calls:** the agent emails a file or a summary during the call.
- **Meeting emails:** templates; the change-time and cancel page; a thank-you afterwards; "sorry we missed you" with a
  rebook link.
- **Smaller emails:** call-back booked; voicemail left; "sorry we missed you" when nobody answered a live chat; "email
  me this chat" in the widget.
- **Templates and files:** templates (blocks, brand kit, placeholders, languages, ready-made sets); Files for email;
  tracked links and downloads; signatures; the owner's daily summary.
- **Limits:** AI emails count as AI replies; plan limits on emails (section 8).
- **Done when:**
  - On local, a real chat gets the welcome email in a Gmail inbox within 3 minutes of going quiet, with the brochure
    and the right first name.
  - A call through the tunnel ends with a recap email whose answers match the knowledge and whose meeting invite opens
    in Google Calendar.
  - During the call, "email me the price list" arrives before the call ends.
  - `compose_probe.py` on 30 real transcripts finds no invented number.
  - Tests and browser checks pass.

### Phase 2: replies come back
- **Receiving:**
  - `reply.nimmiai.in` receives mail (its MX record points to Resend);
  - each email's Reply-To is its conversation's address;
  - replies are matched, cleaned, stored and forwarded to the business;
  - the team's answers from Gmail are relayed.
- **Stop on reply:** every automation stops (and, from phase 4, every journey), and the team is alerted.
- **The AI reads each reply** (a question, call me, a meeting, not interested, stop, an auto-reply, something else) and
  acts per the assistant's setting (answers, drafts, or team only), with the loop guards.
- **Email > Inbox:** assign, notes, templates, "Write with AI", files, the timeline.
- **Done when:**
  - a reply from Gmail to a welcome email shows in the Inbox within a minute and stops the next follow-up;
  - "call me tomorrow at 5" books a call-back at 5 pm;
  - an out-of-office reply gets no answer;
  - an answer from the business's own Gmail reaches the lead from the business's address;
  - tests pass.

### Phase 3: leads from other places
- Lead addresses; the AI reader for portal and form emails; Gmail's forwarding code shown in the dashboard; the
  IndiaMART Push API; a form webhook; the new-lead email and the call within minutes.
- **Done when:**
  - sample lead emails from IndiaMART, JustDial and two property portals become contacts with the right details (real
    emails from customers with names removed, or the owner's own);
  - a lead at 2 pm gets the email in under a minute and the call in under 5 minutes, with calling hours on;
  - tests pass.

### Phase 4: journeys and lead stages
- **Journeys:** triggers, steps, branches, goals, the cap, quiet hours and each person's best hour; the ready-made
  journeys; the step-list builder with "Write with AI".
- **Moved in:** the existing automations and Schedule's follow-up rules.
- **New emails:** the email fallback when the WhatsApp window closes; the customer emails (welcome, review request,
  referral, dates, feedback); answers to unanswered questions for everyone who asked.
- **Lead stages,** owners, tags, the board.
- **Done when:**
  - the "new website lead" journey runs end to end on local with a fake clock (email, WhatsApp, call, waits) and stops
    on a reply at every step;
  - the cap holds across three journeys;
  - the moved automations behave as before;
  - tests and browser checks pass.

### Phase 5: broadcasts
- Segments, consent, scheduling, each person's best hour, subject tests, RSVP, imports, the marketing subdomain,
  reports, and a pause when complaints rise.
- **Done when:**
  - a send to 1,000 people through the fake provider goes at the set pace, with no duplicates across processes;
  - nobody without marketing consent is included;
  - the subject test picks the winner;
  - tests pass.

### Phase 6: tracking, score and reports
- Scanner filtering; engagement in the lead score; "Hot now"; alerts and the optional fast call; reports; the
  deliverability page; events to webhooks and LeadSquared; the business's own link domain.
- **Done when:**
  - scanner clicks are filtered in a test with real scanner patterns;
  - the score changes as designed;
  - reports match the raw events;
  - tests pass.

### Phase 7: the AI email agent and Nimmi
- The agent's levels, the morning approval queue, the hand-over brief, the daily digest; Nimmi's email tools; an
  evaluation on about 50 realistic leads, with the cost per email measured.
- **Done when:**
  - the evaluation meets the owner's bar on the default model (no invented facts, the right language, the right next
    step);
  - the cost per email is written down;
  - the owner approves the default level.

### Phase 8: Gmail, Outlook and calendars
- Google's and Microsoft's app verification (on the owner's accounts; it takes weeks); the send-only connection; the
  relay for replies; calendar free/busy and events.
- **Done when:**
  - a team member's Gmail sends a follow-up that arrives from their own address, and the reply comes back to Nimmi;
  - a meeting booked by the agent appears in the connected calendar.

### Phase 9: scale
- **Amazon SES** (with tenants) when volume makes it cheaper: Resend Scale costs $90 per 100,000 emails, SES about $10.
- **Dedicated IPs.**
- **BIMI:** the business's logo next to its emails in Gmail. It needs DMARC at quarantine or reject, and a paid mark
  certificate.
- **CRM sync** (Zoho, HubSpot, Salesforce); more languages; jobs that delete old data on schedule.

## 8. Plans and prices (a proposal; the owner decides)

Cost basis:
- **Sending:** about ₹0.03 to ₹0.08 an email on Resend (Pro: $35 for 100,000; Scale: $90 for 100,000; overage $0.90
  per 1,000). About ₹0.01 on SES.
- **An AI-written email:**
  - about ₹0.11 on GPT-OSS 120B, or about ₹1.15 on Gemini 3.6 Flash;
  - plus about ₹0.03 for the check on GPT-OSS 20B.

  These come from the list prices in `voice/ai_models.py` at ₹85 a dollar, assuming 6,000 tokens in and 600 out;
  phase 1 measures them.
- **Resend's plan:** Pro ($20 a month) now; Scale ($90) once more than about 8 customers connect their own domains (Pro
  allows 10 domains in all).

Proposal. It must stay equal to the website's pricing table (`dashboard/src/lib/plans.ts`), which a test checks.

| | Starter | Growth | Pro |
|---|---|---|---|
| Alerts to your team | yes (new: today they need Growth) | yes | yes |
| Welcome email after a chat | yes: from Nimmi's sending domain, one template | yes | yes |
| After-call and meeting emails | - | yes | yes |
| Your own domain, files, templates, brand | - | yes | yes |
| Replies come back (Inbox), AI answers | - | yes | yes |
| Broadcasts | - | 5,000 people a month | 25,000 a month |
| Journeys | - | email and WhatsApp | with calls too |
| Leads from portals and forms | - | forwarded emails | plus IndiaMART Push |
| AI email agent | - | drafts | automatic within limits |
| Gmail / Outlook connection | - | - | yes |
| Customer emails included a month | 500 | 5,000 | 20,000 |
| More emails | - | packs, e.g. 10,000 for ₹799 | same |

For example, a Growth customer that uses all 5,000 emails costs about ₹150 to ₹400 to send (AI writing is counted in
its AI replies). That is small next to ₹2,499.

## 9. Risks and what handles them

- **One customer's bad mail spoils Nimmi's shared sending domain.** Own domains are encouraged (Growth). Each workspace
  has limits and a warm-up; complaints are watched, with an automatic pause; templates are checked; new workspaces
  start with low limits.
- **Strangers' addresses typed into a chat.** Each address gets an email once a day at most; there are daily caps and
  the MX check; the email carries a "not you? ignore this email" line; nothing goes as marketing without consent.
- **The AI writes something wrong.** Facts only; the number check; a review by a fast model; review-first mode; and
  every AI email is kept with what it was written from.
- **Email loops with auto-replies.** Header detection, and caps per conversation.
- **Privacy (DPDP from May 2027).** Consent records, retention, erase, and the processor role; a legal review before
  May 2027.
- **Google and Microsoft change their rules.** Follow their sender guidelines; watch bounce and complaint rates; use
  Postmaster Tools.
- **AI capacity on free tiers.** About one AI email a minute per model on Groq's free tier; a paid tier before wide use.
- **Costs grow with volume.** Plan limits, packs, and SES at scale.
- **Building too much.** Each phase is useful alone. Phases 0 to 2 come first; use is measured before phases 4 to 9.

## 10. Decisions for the owner

1. **Start phase 0 now?** It includes your part:
   - **Railway:** backend service > Variables > New Variable: `RESEND_API_KEY` (from resend.com > API Keys).
   - **Resend domain:** resend.com > Domains > Add Domain: `mail.nimmiai.in`. Then add the records it shows in GoDaddy
     (My Products > nimmiai.in > DNS > Add New Record), then press Verify in Resend. Resend's records go on subdomains,
     so Google Workspace mail on nimmiai.in isn't affected.
   - **Resend webhook** (after phase 0 is live): resend.com > Webhooks > Add Endpoint:
     `https://api.nimmiai.in/api/email/webhooks/resend`, all email events. Put its signing secret in Railway as
     `RESEND_WEBHOOK_SECRET`.
   - **DMARC:** nothing to add. `_dmarc.nimmiai.in` already exists (read 1 Nov 2026: `v=DMARC1; p=quarantine; adkim=r;
     aspf=r; rua=mailto:dmarc_rua@onsecureserver.net;`, GoDaddy's own). A second `_dmarc` record would break DMARC.
2. **Resend plan:** upgrade to Pro ($20 a month) now, and to Scale ($90) when customers' domains pass about 8?
3. **Plans** (section 8): which plan gets what, the email allowances and the packs. Team alerts on every plan (today
   they need Growth)?
4. **A "Sent with Nimmi" line** in Starter emails, like the widget's watermark?
5. **Replies through Nimmi** (`reply.nimmiai.in`), with a copy forwarded to the business: OK? It is one MX record in
   GoDaddy for the `reply` subdomain only.
6. **Defaults:** welcome and meeting emails automatic; the after-call email "review first" for the first 20, then
   Nimmi suggests automatic?
7. **Broadcasts:** only from the business's own domain (this protects everyone), or also from Nimmi's domain with low
   limits?
8. **Phase 8** needs Google's and Microsoft's app verification: privacy policy and terms pages with your business
   details, and a demo video; Google takes weeks. Start the paperwork early?
9. **Lead portals:** which first (IndiaMART, JustDial, 99acres, MagicBricks, Sulekha)? Do you or your customers have
   accounts, to get sample emails?
10. **Keeping data:** how long to keep email text (12 months by default)? A business postal address in footers? (It is
    needed for customers who email people in the US.)
11. **OK to read counts from live** (read-only): how many chats and calls collect an email, to size the allowances?
12. **The email agent's default level** (phase 7): off (today), or Drafts only for new Growth and Pro customers?

## 11. Status

1 Nov 2026: plan written.

Phase 0 built 1 Nov 2026 and live the same day (df95395):
- Done as planned:
  - Resend's signed webhook with bounces, spam reports, suppressions and failures;
  - text filled in at send time, idempotency keys, tags;
  - the unsubscribe page that asks first, with offers-only and resubscribe;
  - address checks (format, typo, throwaway inboxes, MX);
  - the business's own domain from the dashboard (records, checks, a sending-only key, warm-up);
  - senders per assistant;
  - email-only chat leads as contacts;
  - meeting emails with the business's Reply-To;
  - the Email section (Overview, Automations, Bulk email, History, Settings).
- Added along the way:
  - bulk email pauses above Gmail's spam limit;
  - the widget's "Did you mean";
  - Nimmi (the dashboard's agent) can read all of it and change who emails come from;
  - backups never run from a developer's machine (it had the live storage keys).
- Checks:
  - 418 backend tests pass (`test_mail_foundation.py` 13, plus the backup test);
  - three of the new tests were checked to fail without their fix;
  - browser `email_ui.mjs` 29 of 29.
- Set up by the owner, 1 Nov 2026: `nimmiai.in` and `mail.nimmiai.in` verified in Resend (8 DNS records in GoDaddy; the `_dmarc`
  record GoDaddy already had stays).
- Still to do on Railway: `RESEND_API_KEY` (Full access), `CUSTOMER_EMAIL_FROM`, the Resend webhook and `RESEND_WEBHOOK_SECRET`.

The owner's decisions, 1 Nov 2026 (section 10):
- Starter gets team alerts and a plain welcome email from Nimmi's address; Growth and Pro get everything else.
- The after-call email starts on review first; after 20 approved emails Nimmi offers automatic.
- No "Sent with Nimmi" line.

Phase 1, as of 1 Nov 2026:
- Built:
  - each assistant's own emails, designs with blocks in English, Tamil and Hindi, the editor with a live preview and a test send;
  - tracked links and downloads;
  - the welcome email after a quiet chat, with the AI's note and files;
  - the after-call email (section 5.3), with Email > Drafts and the offer to go automatic;
  - Nimmi's tools for all of it.
- Built since (local until pushed): the `send_email` call tool; meeting emails from the design, with the change-time and cancel page; the
  thank-you and rebook emails; call-back booked; voicemail; missed live chat; "email me this chat"; the book and call pages; the daily
  summary.
- Not built: plan limits on the number of emails (section 8 needs the owner's numbers); a WhatsApp chat's welcome email is still only as
  good as the chat collecting an address.
- Checks:
  - backend tests in `test_mail_designs.py` and `test_after_call_email.py`; ten safeguards of the after-call email were each
    switched off once to confirm a test fails without them;
  - browser `email_design_ui.mjs`, `email_drafts_ui.mjs`;
  - `compose_probe.py` on 8 real calls: no invented number (the plan's 30 are still to run, as more real calls come in).
- Not tried yet: a real call ending in a real email in a Gmail inbox ("Done when", above).

Phase 2, as of 1 Nov 2026 (built locally, off until `REPLY_DOMAIN` is set):
- Changed from the plan: replies use `mail.nimmiai.in`, which already sends, rather than a new `reply.nimmiai.in`. Turning receiving on
  there is one switch and one MX record.
- Built: reply addresses per conversation; receiving, once each, with the mail server's checks; the team's answers from their mailbox;
  stop on reply; the AI reading each reply, per assistant (ai, draft, team), with Schedule bookings; Email > Inbox; Nimmi's tools.
- Added along the way: a reply address that can't receive mail is refused; the AI answers only the person in the conversation.
- Left for later: cleaned HTML view of emails (they're shown as text), assigning from the page, templates in the reply box, the timeline
  of chats and WhatsApp beside a conversation (the person's details and calls show today), letting agents (not only owners and admins)
  use the Inbox, meeting emails carrying the conversation's address.
- Checks:
  - `test_email_replies.py`; eleven safeguards were each switched off once to confirm a test fails without them;
  - browser `email_inbox_ui.mjs`, with Resend faked and the real AI answering.
- Not tried yet: a real reply from Gmail through Resend (it needs receiving on and `REPLY_DOMAIN` on Railway).

Phase 3, as of 1 Nov 2026 (built locally):
- Changed from the plan: lead addresses are at `REPLY_DOMAIN` (`leads-<code>@mail.nimmiai.in`), so no new `in.nimmiai.in` domain.
- Built: forwarding addresses, with Gmail's code on the page; the AI reader for any format, which can't invent a detail; IndiaMART's Push API; a
  form link for any website; a contact for each lead, merged; the team told; the new-lead email; the call within minutes on Pro.
- Left for later: real emails from the portals to try the reader on (the plan's "Done when"), WhatsApp to portal leads (rules), the new-lead
  journey (phase 4).
- Checks: `test_lead_intake.py`; browser `email_leads_ui.mjs`.

Phase 4, as of 1 Nov 2026 (built locally):
- Built: journeys (seven triggers, seven kinds of step, goals, the cap, quiet hours, each person's usual hour), eight ready-made journeys written from
  the knowledge, "Write with AI", the email fallback when the WhatsApp window has closed, a feedback page (good or not, with a comment; "not good" tells the
  team), dates in a person's details, stages, owners, tags and the board, answers sent to the people who asked (the team ticks who), Nimmi's tools.
- Changed from the plan:
  - **Not moved in:** the existing automations and Schedule's follow-up rules keep running where they are, and Email > Journeys lists them. Moving a working
    system's settings needs its own care, and a mistake there changes what real customers already get. The cap counts their emails, so a journey never lands
    on top of them; a business that wants a journey to take over turns the old one off.
  - A reply ends every journey with that assistant, whatever its goal: mail that ignores a reply looks like a machine. "They reply" also counts a call or a
    WhatsApp chat.
  - The cap counts everything sent to the person, not only journeys.
  - A journey's call stops at Schedule's 7-day rule, counted from when they came in if they never spoke. It needs follow-ups on in Schedule.
- Left for later:
  - "Left halfway" (gave an email, didn't finish booking), which needs the flow to report where it stopped;
  - round-robin owners;
  - a design for journey emails (they go as plain, personal emails);
  - the cold-lead journey's marketing consent (phase 5 brings consent; today the page says who it's for);
  - "They reply" by email needs receiving on and `REPLY_DOMAIN`; until then only calls and WhatsApp count.
- Known limits: journeys need a contact, so with Remember callers off a chat lead starts none. Stages show on the board, not yet on Contacts.
- Checks: `test_journeys.py` (the whole journey on a fake clock, a reply at every step, each trigger from the real code), `test_question_answers.py`;
  26 safeguards each switched off once to confirm a test fails; real models through `dev-scripts/email/journey_probe.py`; browser `email_journeys_ui.mjs`.
- Not tried yet: a journey on a real phone with real WhatsApp and a real call.

Phase 5, as of 1 Nov 2026 (built locally):
- Built: consent records per assistant (the chat's tick box with the business's words, a form's newsletter field, an import that says how they agreed, the team's note on
  the Lead board; an unsubscribe withdraws it and only the person can give it back); groups by status, stage, source, tags, recent contact and engagement, saved; drafts
  with spam notes and a test to yourself; now, at a time or at each person's usual hour, at 30, 60 or 120 a minute; a subject test on a fifth of the list; a pause by itself
  when spam reports or bounces rise, with resume and cancel; invitations with Yes, Maybe and No and a reminder the day before; CSV imports; reports per send; addresses whose
  domain takes no mail left out; customers' own emails always ahead of bulk email in the queue; `BULK_EMAIL_FROM` for the marketing subdomain.
- Decision 7, taken for now: bulk email can go from Nimmi's address with a daily limit (`BROADCAST_SHARED_DAILY`, 200 per workspace; 0 makes it own-domain only), and from
  a business's own domain with only its warm-up. Change the number on Railway at any time.
- Changed from today: the old bulk email (to anyone who ever shared an email, with one tick box for the whole group) is gone. After the push a workspace's bulk email
  reaches only people with a consent record, so it reaches nobody until consent is collected. Earlier sends stay listed.
- Left for later: double opt-in (a confirmation email before a yes counts: today anyone can type someone else's address into a chat, as on any form); the one-line notice
  under the chat's email question; asking on calls ("Can we email you offers?"); groups by interest or language; "replied" in a send's report counts any reply after it
  started, not only to that email.
- Checks: `test_broadcasts.py`; 26 safeguards each switched off once to confirm a test fails; browser `email_bulk_ui.mjs`; `dev-scripts/email/bulk_probe.py`: 1,000 people
  imported (1.2 s) and sent at 120 a minute through the fake Resend on two server processes: 1,000 emails to 1,000 people, none twice, 122 a minute on average (123 to
  124 in each full minute), all 1,000 reported delivered, no database errors.
- Not tried yet: a real send through Resend (it needs the owner's OK), and the marketing subdomain (it needs `news.nimmiai.in` verified in Resend).

Phase 6, as of 1 Nov 2026 (built locally):
- Built:
  - **Scanner filtering.** Each click is kept with its signals and judged half a minute later. A scanner's or an HTTP library's name in the user agent decides by
    itself, and so do three of an email's links within three seconds. Otherwise points add up: a click within 20 seconds of sending, three links within ten seconds,
    one network opening five or more people's emails within ten seconds, no user agent or no language header. HEAD requests are never clicks. Scanners still get the
    page. The network is kept only as a keyed hash.
  - **The email score on each contact:** a reply 40, Book a time or Call me 30, prices 20, a download 15, any other link 5; each link once; the week before counts
    half; gone after two weeks; opens count for nothing.
  - **Hot now** on Email > Overview; the team's alert ("Meena Iyer just opened Book a time"), once a day per person and action, with a switch.
  - **On Pro, off by default,** a follow-up call ten minutes after someone opens Book a time and doesn't book. Schedule calls it off if they book meanwhile. At most
    once a week.
  - **"In about 5 minutes"** on the email's Call me page during calling hours.
  - **Email > Reports:** each kind of email, journey and bulk email; the funnel from lead to customer; the team's answers and waiting times; deliverability against
    Gmail's limits, scanner clicks left out, DMARC on each domain, the steps for Postmaster Tools.
  - **Events to the business's webhook** (email.sent, replied, clicked, bounced, unsubscribed) **and to LeadSquared** as activities found by email (all but sent),
    kept first and sent with retries, shown in Integrations > Activity.
  - Nimmi's reports tool.
- Changed from the plan:
  - The dashboard alert is the Hot now list: the dashboard has no notification area.
  - The email score is its own number on the contact, beside the AI's rating from calls, not added into the chat and call score (that one is worked out per chat or
    call; the contact is where a lead's emails meet them).
  - Reports per template are the rows per kind of email.
- Left for later: the business's own link domain (`links.theirdomain.in`). It needs a certificate per business on Nimmi's side, like custom domains in Deployments,
  through Cloudflare for SaaS, which isn't set up on live yet.
- Checks: `test_clicks.py` (real scanner patterns: a Safe Links sweep, gateways, scanners and libraries that name themselves, HEAD; and people: a fast click, two
  links in a row, one office clicking minutes apart), `test_engagement.py`, `test_outbox.py`, `test_reports.py` (every number against the raw events); 35 safeguards
  each switched off once to confirm a test fails; browser `email_reports_ui.mjs`. The test browser itself, which says HeadlessChrome, was rightly filtered as a
  scanner until the check gave it a person's browser identity.
- Not tried yet: real scanners on real mail (it needs live sending), a real LeadSquared account.

Phase 7, as of 1 Nov 2026 (built; the default level waits for the owner):
- Built:
  - **The email agent,** one per assistant, off until someone turns it on (Automations, Growth up). Each hour from 9 am to 7 pm India time (8 am for the morning queue) it
    looks at leads who went quiet and does one of four things: an email that answers what they left open, a hand-over to the team, wait, or stop.
  - **Levels:** Drafts only (each email waits for the team); Morning approval (written at 8 am, what the team approves goes, the rest is dropped at midnight); Automatic
    (goes by itself, within the limits). A daily limit per assistant, 20 to start, 200 at most. Anything a check doubts waits for a person on every level.
  - **Who it leaves alone, in code, not left to the model:** customers, lost leads, anyone not interested; anyone unsubscribed, bounced or on the do-not-email list; people on
    a journey; anyone whose reply waits for the team; anyone in touch in the last two days; enquiries over 30 days old without a marketing consent record; more than 3 of its
    emails in a month, or 2 unanswered; 90 days after it stopped for someone, a week after a hand-over, a day after it waited or failed; anyone at the shared email cap.
  - **What it may say:** one model decides and writes; numbers the sources don't have are removed (`keep_known_numbers`); the language is checked by script and written again
    once; a second model checks facts, language and promises and can hold it. The history is boxed as data. It counts as one AI reply.
  - **The hand-over brief** (what they want, what they were told, the next step) on the lead's card on the Lead board, a to-do for the team, and one email a day per person.
  - **The daily summary** says what it wrote and handed over. **Email > Drafts** has its emails on top: why it wrote each, change, send, drop, or send all the ready ones
    (not the held ones).
  - **Nimmi:** sets the agent's level (undoable), reports what it did, drafts a bulk email for a group ("warm leads who asked about 2BHK": a new "contains" rule), and sends
    it only after Confirm.
  - Token use is recorded per model call (`ai.METER`), so cost is measured from what each service reports.
- Evaluation (`dev-scripts/email/agent_eval.py`, real models, 5 businesses x 10 situations, 50 leads). The last run:

  | Measure | Result |
  |---|---|
  | The right next step | 50 of 50 |
  | Emails written | 35 |
  | Emails with a number the sources don't have | 0 |
  | Emails in the wrong language | 0 |
  | Emails saying something was done or promising a call, visit or discount | 0 |
  | Emails held for a person | 0 |
  | Cost per email written | Rs 0.117 |
  | Cost per decision | Rs 0.094 on average, Rs 0.302 at most |
  | Time per decision | 3.1 s on average, 5.8 s at most |

  - The prompts were tuned on these same 50 leads over six runs (right step: 43, 47, 48, 44, 50, 50), so this is not a test on unseen leads. Four new leads in the browser check
    (`email_agent_ui.mjs`, real AI: English, Tamil, an objection, someone ready to buy) all went the right way, in 12.6 s for the four.
  - Models that answered: Gemini 3.5 Flash-Lite 48 times, Qwen 3.8 27B 18, GPT-OSS 20B 19. Gemini's free daily quota ran out in the first run, and the backups took over.
  - What the runs taught: models get day counts wrong, so code works them out and today's date is given; an order of decisions (stop, hand over, email, and only then wait) was
    needed before "too expensive" got an answer; a checker told "disputes wait for a person" held everyday price questions, so it now judges only facts, language and promises.
- Changed from the plan: replies are still handled by phase 2 (settings per assistant), not by the agent.
- Left for later: "left halfway" journeys; a page listing everything the agent did (Nimmi can read it today).
- Checks: `test_email_agent.py` (34); 26 safeguards each switched off once to confirm a test fails (two were found untested and got tests); the isolation test now covers its
  drafts and also fails if one workspace adds rows to another's; browser `email_agent_ui.mjs` (39 steps).
- **The owner's part:** approve the default level (decision 12). It stays off, for everyone, until then.
- Pushed to live 2 Nov 2026 with phases 1 to 6, after every test and browser check ran on a real Postgres (`dev-scripts/postgres`).

Phase 8, as of 2 Nov 2026 (built and tested against fakes; nothing shows on live until the owner has apps at Google and Microsoft):
- Built:
  - **Connecting** (Email > Settings > Mailboxes and calendars, `mail/mailbox.py`, `connections_api.py`): each person connects their own Gmail or Outlook. Send-only: `gmail.send`, `Mail.Send`. Asking
    to read mail would be a restricted scope at Google, with a yearly security audit. Tokens sealed with secretbox. The provider sends them back to the dashboard page, which finishes with the
    signed-in person's token, so a link someone else started can't attach their mailbox to another workspace.
  - **What goes from a mailbox:** per assistant, the email agent's emails, after-call emails and journeys; the team's answers go from the mailbox of whoever answers, else the assistant's. Never bulk
    or welcome emails. Reply-To stays Nimmi's reply address, so replies come back to the Inbox with no read access. Sent as whole MIME on both, because Graph's JSON form only takes `x-` headers.
  - **It never holds up an email:** 200 a day per mailbox (`MAILBOX_DAILY_LIMIT`; Google allows 500 for a free Gmail, 2,000 for Workspace), an hour's pause after the provider's own limit, and when it needs
    connecting again the person is told once. In all these cases the email goes the usual way.
  - **Calendars** (`voice/calendars.py`, chosen in Schedule > Settings): busy times are read every 5 minutes and kept on the connection, so a live call never waits for Google. They come off the times
    offered on calls and on the booking page. Each confirmed meeting becomes an event, with a Meet or Teams link when that's on; moved, cancelled and failed ones follow on the next pass. Nobody is
    invited through Google or Microsoft: the person hears from Nimmi, once. Outlook's busy times come from calendarView, because getSchedule refuses personal accounts.
- Facts checked 1 Nov 2026 (Google's and Microsoft's own pages):
  - `gmail.send` is sensitive: verification, no security assessment. Asking for `gmail.readonly` as well would make the whole app restricted ([Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)).
  - The narrowest calendar pair is `calendar.freebusy` + `calendar.events.owned` ([Calendar scopes](https://developers.google.com/workspace/calendar/api/auth), [freeBusy](https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query)). Check the pages' labels in the Cloud console.
  - While a Google app is in Testing, refresh tokens last 7 days and only listed test users can connect. A password change also ends tokens with Gmail scopes ([OAuth 2.0](https://developers.google.com/identity/protocols/oauth2)).
  - Graph's sendMail takes base64 MIME with `Content-Type: text/plain` ([MIME](https://learn.microsoft.com/en-us/graph/outlook-send-mime-message)). getSchedule doesn't support personal accounts ([getSchedule](https://learn.microsoft.com/en-us/graph/api/calendar-getschedule?view=graph-rest-1.0)).
  - Multi-tenant apps from unverified publishers can't get user consent ([consent](https://learn.microsoft.com/entra/identity-platform/application-consent-experience)). Teams links through `isOnlineMeeting` are documented for work accounts only.
- Changed from the plan: the redirect goes to the dashboard, not an API callback, for the reason above; the customer isn't an attendee on the event (Outlook would email them an invitation of its own).
- Honest limits:
  - **Not tried against real Google or Microsoft.** Everything ran against `dev-scripts/email/fake_mailbox.py`, written from their documents. The first real connection is the real test.
  - Delivery isn't reported for mailbox emails: Gmail and Outlook send no delivery or bounce events to Nimmi, and a bounce lands in that person's mailbox. So those emails show as sent, never as
    delivered, in History and Reports. Clicks and replies are counted as usual.
  - Personal Outlook accounts get the calendar event but may not get a Teams link; the default link stays.
- Checks: `test_mailbox.py` (44, on SQLite and Postgres); 46 safeguards each switched off once (3 were covered only by a second layer and got tests of their own); browser `email_mailbox_ui.mjs` (46 steps on
  Postgres, real AI for the agent's emails); the isolation test covers connections.
- **The owner's part, Google** (decision 8; needs privacy policy and terms pages, and a demo video):
  1. console.cloud.google.com > your project > APIs & Services > Library: enable Gmail API and Google Calendar API.
  2. APIs & Services > Credentials > Create Credentials > OAuth client ID > Web application. Authorized redirect URI: `https://nimmiai.in/dashboard/email/settings`.
  3. Google Auth Platform > Data Access > Add or remove scopes: `gmail.send`, `calendar.freebusy`, `calendar.events.owned`. Audience: add test users, then submit for verification.
  4. Railway > backend service > Variables: `GOOGLE_MAIL_CLIENT_ID`, `GOOGLE_MAIL_CLIENT_SECRET`.
- **The owner's part, Microsoft:**
  1. entra.microsoft.com > App registrations > New registration. Supported account types: any organizational directory and personal Microsoft accounts. Redirect URI (Web): `https://nimmiai.in/dashboard/email/settings`.
  2. API permissions > Add a permission > Microsoft Graph > Delegated: `Mail.Send`, `Calendars.ReadWrite`, `User.Read`, `offline_access`.
  3. Certificates & secrets > New client secret. Note when it expires.
  4. Branding & properties > Publisher verification (needs a Microsoft partner account).
  5. Railway: `MICROSOFT_MAIL_CLIENT_ID`, `MICROSOFT_MAIL_CLIENT_SECRET`.

## Words used

- **SPF, DKIM, DMARC:** DNS records that prove an email really comes from the domain it says. DMARC tells mail
  services what to do when the proof fails.
- **MX record:** says which server receives a domain's mail.
- **Bounce:** the email couldn't be delivered. A hard bounce means the address doesn't exist.
- **Complaint:** the person pressed "Report spam".
- **Suppression:** an address Nimmi won't email again.
- **Warm-up:** sending a little at first from a new domain, then more, so mail services learn to trust it.
- **Idempotency key:** a label on each send, so the same email can't go twice even if the request is repeated.
- **Journey:** a planned set of steps for a lead (emails, WhatsApp, calls, waits) that stops when they respond.
