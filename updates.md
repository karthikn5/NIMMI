# Nimmi AI: modules and features to add

Research notes on what Nimmi could add next, beyond integrations. Based on what's already built, the Retell AI research, and what's known of competing products in India (Wati, Interakt, AiSensy, Gallabox, Yellow.ai, Haptik, Intercom, Tidio, Vapi, Bland). Market details weren't freshly re-checked online, so verify them before committing to a build.

**Already built (not repeated below):** website chat widget, flow builder, live chat with handoff, voice agents (inbound and outbound), call-backs, campaigns, phone numbers, collected data, WhatsApp AI chat, email automation, webhooks, LeadSquared, Google Sheets flow block, analytics, team roles, billing.

Effort: **S** = days, **M** = 1 to 3 weeks, **L** = 1 month or more.

## 1. Conversations and customers (the biggest gap)

| Module | What it does | Effort |
|---|---|---|
| **Unified inbox** | Web chat, WhatsApp, calls and email in one inbox, one thread per customer | L |
| **Contacts / mini CRM** | One profile per person: every chat, call, field collected and order, merged by phone and email | M |
| Tags and segments | Label contacts (hot lead, paid, Tamil speaker) and build lists from filters | S |
| Assignment rules | Round-robin, by language, by assistant or by business hours | M |
| Saved replies | Answers your team reuses in Live chat, with `{{name}}` placeholders | S |
| Internal notes and @mentions | Private team comments inside a conversation | S |
| Reply-time targets | "First reply within 5 minutes" timers, with alerts when missed | M |
| Agent mobile app | Answer handoffs from a phone, with push notifications | L |

## 2. More channels

| Module | What it does | Effort |
|---|---|---|
| Instagram DMs | AI replies to DMs and story replies, with the same knowledge as the website | M |
| Facebook Messenger | Same as above | M |
| SMS (DLT-registered) | OTPs, reminders and fallback when WhatsApp fails (Indian DLT rules apply) | M |
| Email inbox bot | AI drafts or sends replies to the support@ inbox | M |
| RCS business messaging | Rich messages in Android's default SMS app; emerging in India | L |
| WhatsApp Flows | In-chat forms (booking, lead forms) inside WhatsApp | M |
| Click-to-WhatsApp ads | Track which Meta ad brought each lead | M |
| Web call button | "Talk to us" on the website, which starts a voice call in the browser | S (the engine exists) |
| Telegram | For education and community businesses | S |

## 3. Sales and commerce (direct revenue for customers)

| Module | What it does | Effort |
|---|---|---|
| **Appointment booking** | Google Calendar or Cal.com slots, booked by chat, WhatsApp or voice, with reminders | M |
| **UPI payment links** | Razorpay link sent in chat or WhatsApp; the assistant confirms when paid | M |
| **COD confirmation calls** | Voice calls to confirm cash-on-delivery orders before dispatch; big for Indian D2C | M (built on campaigns) |
| Failed-delivery calls | Ask why a delivery failed and reschedule it | M |
| Product catalogue | The assistant answers from products, prices and stock, and sends product cards | M |
| Shopify / WooCommerce | Order status lookup and abandoned-cart recovery on WhatsApp | M |
| Quotes and GST invoices | Generate a PDF quote or invoice from a conversation | M |
| Lead scoring | Score each lead from the fields collected and the conversation | S |

## 4. Marketing and growth

| Module | What it does | Effort |
|---|---|---|
| **WhatsApp broadcasts** | Approved template campaigns to segments, with delivery, read and reply stats; Wati and Interakt's core product | L |
| Drip sequences | Day 0 / 2 / 7 follow-ups across WhatsApp, email and calls | M |
| Proactive website messages | "Need help choosing a plan?" after 20 seconds on the pricing page | S |
| Lead forms and landing pages | Hosted forms that feed the assistant and the contacts list | M |
| QR codes | QR code that starts a WhatsApp chat or call-back, with tracking per poster or store | S |
| Missed-call campaigns | Customer gives a missed call, the AI calls back; a common Indian marketing pattern | M |
| Referral tracking | Referral links and codes recorded on each lead | S |
| Greeting A/B tests | Test two greetings and keep whichever captures more leads | S |

## 5. AI and knowledge quality

| Module | What it does | Effort |
|---|---|---|
| **Unanswered questions** | List what the assistant couldn't answer, with one-click "add the answer" | M |
| Answer corrections | Fix an answer once and it's reused next time | M |
| Website auto-sync | Re-read the site weekly and update the knowledge | M |
| Google Drive / Notion sources | Use documents as knowledge, kept in sync | M |
| Custom actions | The assistant calls the business's APIs mid-chat or mid-call ("check my order status") | M |
| WhatsApp voice notes | Transcribe voice notes in Tamil, Hindi and other languages, then reply; very common in India | S (Sarvam is already connected) |
| Image understanding | The customer sends a photo (damaged product, prescription) and the assistant understands it | M |
| Sentiment escalation | Angry customer → hand to a person automatically | S |
| Automatic QA scoring | Score every chat and call for accuracy, tone and policy, and flag bad ones | M |
| Specialist assistants | A "router" passes the conversation to a sales, support or billing assistant | M |

## 6. Voice, next level

| Module | What it does | Effort |
|---|---|---|
| **Live call monitoring** | Listen in, whisper to the AI, or take over the call | L |
| Keypad (IVR) menus | "Press 1 for sales", and capturing digits like an order ID or PIN | M |
| Auto language detection | The caller switches to Tamil mid-call and the assistant follows | M |
| Business hours and holidays | Different greeting and behaviour after hours | S |
| Inbound queue | Hold sound when all lines are busy, plus a call-back offer | M |
| Brand voice | Custom or cloned voice for a business (needs consent) | L |
| Number masking | The agent and customer never see each other's real numbers | M |
| Recording redaction | Remove card numbers and Aadhaar numbers from recordings and transcripts | M |

## 7. Analytics and reports

| Module | What it does | Effort |
|---|---|---|
| Conversion funnel | Visitor → chat → lead → booked → paid, per channel and campaign | M |
| Topic clustering | "What are people asking about this week?" | M |
| Satisfaction surveys | One tap after a chat, one keypress after a call | S |
| Team performance | Reply time, resolution and handled count per teammate | S |
| Scheduled reports | Weekly summary on email or WhatsApp to the owner | S |
| Revenue attribution | Which campaign or ad produced paid customers | M |

## 8. Agencies and administration (a big Indian growth channel)

| Module | What it does | Effort |
|---|---|---|
| **Agency / white-label mode** | Agencies manage many client workspaces under their own brand and pricing | L |
| Public API and keys | Customers build on Nimmi | M |
| Audit log | Who changed what, and when | S |
| Two-factor login and SSO | Security for larger customers | M |
| Workspace usage limits | Caps and alerts on minutes, messages and spending | S |

## 9. Compliance and trust (required to sell to bigger Indian businesses)

| Module | What it does | Effort |
|---|---|---|
| **DPDP compliance centre** | Consent records, data export and deletion requests, under the DPDP Act 2023 and its rules | M |
| PII redaction | Mask Aadhaar, PAN and card numbers in transcripts | M |
| Data stored in India | Region choice for storage | M |
| Security page and status page | Uptime and incident history | S |

## 10. Billing and growth for Nimmi itself

- Usage-based plans (per conversation or minute)
- GST invoices
- Free trial with guided setup
- Coupons
- Affiliate programme
- Annual plans
- Setup wizard ("connect WhatsApp in 5 minutes")

## 11. Ready-made templates by industry

Ready-made assistant, flow, fields and campaign templates for:

- Real estate (site visits)
- Coaching and colleges (admissions)
- Clinics (appointments, reminders)
- Restaurants (table booking)
- D2C shops (COD, returns)
- Salons
- Travel
- Insurance and loans (lead qualification)

Cheap to build, and they make setup take minutes instead of hours.

## 12. More integrations

Zoho CRM (very popular in India), HubSpot, Salesforce, Freshsales and Freshdesk, Pipedrive, Shopify, WooCommerce, Razorpay, Google Calendar and Cal.com, Slack, Microsoft Teams, Notion, Zapier and Make app listings, and Tally exports.

---

## Recommended build order: top 10

1. **Contacts and unified inbox:** the foundation that almost everything else plugs into.
2. **WhatsApp broadcasts:** what Indian businesses pay for most, and the WhatsApp connection already exists.
3. **Appointment booking:** works across chat, WhatsApp and voice at once.
4. **WhatsApp voice notes:** small effort, a big difference for Indian users, and Sarvam is already connected.
5. **Unanswered questions loop:** makes every assistant better week by week.
6. **COD confirmation calls:** a clear money use case for D2C, built on the existing campaigns.
7. **UPI payment links:** turns conversations into payments.
8. **Industry templates:** fastest way to improve sign-up-to-success rates.
9. **DPDP compliance centre:** needed before larger customers will buy.
10. **Agency / white-label mode:** agencies resell Nimmi to many small businesses.
