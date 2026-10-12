# Complete Requirements & API Procurement Guide
**Platform: Nimmi AI (Chatbot + Voice AI SaaS for India)**
*A comprehensive guide covering every API, service, document, and configuration required from your end to complete and launch the platform.*

---

## 1. Executive Checklist: What You Need to Procure

Here is the master summary table of all services, APIs, and accounts categorized by implementation phase, estimated cost, and urgency:

| Category | Service / Provider | Purpose in Nimmi AI | Signup URL | Est. Monthly Cost (INR) | Priority |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Speech-to-Text (STT)** | **Sarvam AI** (Saaras v4) | Real-time Indian speech recognition (English, Tamil, Hindi, Hinglish, Tanglish) | [sarvam.ai](https://www.sarvam.ai/) | ₹30 / hr (~₹500 - ₹1,500/mo) | **Critical (Phase 1)** |
| **Text-to-Speech (TTS)** | **Sarvam AI** (Bulbul v4 Flash) | Natural Indian accent speech generation | [sarvam.ai](https://www.sarvam.ai/) | ₹30 / 10k chars (~₹300 - ₹1,000/mo) | **Critical (Phase 1)** |
| **Fast LLM Inference** | **Google Gemini** (Gemini 2.0 Flash) | Ultra-fast RAG reasoning & dialogue generation | [aistudio.google.com](https://aistudio.google.com/) | Pay-as-you-go (~₹200 - ₹800/mo) | **Already have key** |
| **Fast LLM Fallback** | **Groq Cloud** (Llama 3.3 70B) | Sub-150ms latency LLM response for voice interruptions | [console.groq.com](https://console.groq.com/) | Free tier available / ~$0.59/1M tokens | **High (Phase 1)** |
| **Vector Database** | **Pinecone** (Serverless) | Document chunking, vector embeddings, semantic search | [pinecone.io](https://www.pinecone.io/) | Free tier ($0) / Pay-as-you-go | **Already have key** |
| **WebRTC Media Server** | **LiveKit Cloud** | Real-time WebRTC audio streaming between user & AI | [livekit.io](https://cloud.livekit.io/) | Free tier (50GB / mo) ➔ $0 to start | **Critical (Phase 1)** |
| **Indian Telephony / SIP** | **Plivo (India Region)** or **Exotel** | Inbound & Outbound phone calls (PSTN mobile/landline) | [plivo.com](https://www.plivo.com/) / [exotel.com](https://exotel.com/) | ~₹0.38 - ₹0.50 / min + DID rental (~₹1,500 - ₹3,000/mo) | **Phase 2 (Phone Launch)** |
| **Payment Gateway** | **Razorpay** (Live Mode) | Collecting subscription payments & prepaid minute top-ups | [razorpay.com](https://razorpay.com/) | 2% per transaction + 18% GST | **High (Activate Live Mode)** |
| **Auth & Database** | **Supabase** (PostgreSQL) | User authentication, database, session management | [supabase.com](https://supabase.com/) | Free tier ➔ $25/mo Pro tier (~₹2,100/mo) | **Already have key** |
| **Cloud Hosting** | **Railway** or **VPS (Hetzner / AWS)** | Hosting FastAPI backend, WebSockets, Next.js dashboard | [railway.app](https://railway.app/) | $5 - $20/mo (~₹450 - ₹1,800/mo) | **Already active** |
| **Transactional Email** | **Resend** or **SendGrid** | Password reset emails, lead alerts to business owners | [resend.com](https://resend.com/) | Free tier (3,000 emails/mo) ➔ $0 | **High (Phase 1)** |
| **Custom Domain & DNS** | **Cloudflare** + Registrar | Custom brand domain (e.g. `nimmiai.in`) & SSL certificates | [cloudflare.com](https://www.cloudflare.com/) | ~₹600 - ₹1,000 / year | **High (Phase 1)** |

---

## 2. Detailed Breakdown of Each API & Service

### A. Voice AI Engine (The Core Add-on)

#### 1. Sarvam AI (Indian Speech AI — STT & TTS)
* **Why it is needed**: US providers (OpenAI Whisper, ElevenLabs) struggle with regional Indian phonetics, Indian English accents, and vernacular code-mixing (Tamil + English = Tanglish; Hindi + English = Hinglish). Sarvam AI is specifically trained for 22 Indian languages and delivers the most natural-sounding Indian voices on the market.
* **Models to use**:
  - **Saaras v4** for real-time streaming Speech-to-Text via WebSocket.
  - **Bulbul v4 Flash** for sub-200ms streaming Text-to-Speech.
* **Pricing**:
  - STT: ₹30 per hour (₹0.50/min).
  - TTS: ₹30 per 10,000 characters (~₹0.24/min).
* **Where to get it**: [https://www.sarvam.ai/](https://www.sarvam.ai/) ➔ Register for an API key. New accounts receive ₹1,000 free testing credits.
* **Environment variables needed**:
  ```env
  SARVAM_API_KEY=your_sarvam_api_key_here
  ```

---

#### 2. LiveKit Cloud (Real-time Audio Streaming & WebRTC)
* **Why it is needed**: Audio must flow seamlessly between the user's microphone and your backend AI models with zero buffering. LiveKit provides a battle-tested WebRTC infrastructure and open-source **LiveKit Agents framework** that glues STT + LLM + TTS together with built-in voice activity detection (VAD) and interruption handling (barge-in).
* **Pricing**: 
  - Free Tier includes **50 GB/month bandwidth** and **100 concurrent rooms** (ample for all initial tests and pilots).
  - Paid tier: Pay-as-you-go based on egress bandwidth ($0.05/GB).
* **Where to get it**: [https://cloud.livekit.io/](https://cloud.livekit.io/) ➔ Create a project ➔ Generate API Key & Secret.
* **Environment variables needed**:
  ```env
  LIVEKIT_URL=wss://your-project.livekit.cloud
  LIVEKIT_API_KEY=your_livekit_api_key
  LIVEKIT_API_SECRET=your_livekit_api_secret
  ```

---

#### 3. Groq Cloud (Ultra-Fast LLM Inference Fallback)
* **Why it is needed**: When talking over voice, users expect immediate responses. Groq runs Llama 3.3 70B at **~300 tokens/second** with a Time-to-First-Token (TTFT) under **150ms**, ensuring the AI replies before awkward silence occurs.
* **Pricing**:
  - Generous free tier available for development.
  - Paid: $0.59 / 1M input tokens, $0.79 / 1M output tokens (mere paise per conversation).
* **Where to get it**: [https://console.groq.com/keys](https://console.groq.com/keys) ➔ Create free API key.
* **Environment variables needed**:
  ```env
  GROQ_API_KEY=gsk_...
  ```

---

### B. Telephony & Calling Infrastructure (For Real Phone Calls)

#### 4. Indian Cloud Telephony Provider (Plivo or Exotel)
* **Why it is needed**: To allow the AI to receive calls from regular mobile phones/landlines and dial outbound phone numbers across India.
* **Options to choose from**:
  1. **Option A: Plivo (India Region)** *(Recommended for faster technical setup)*:
     - Directly provides SIP Trunking and in-country call routing compliant with Indian regulations.
     - Outbound rate: **~₹0.38 - ₹0.45 per minute**.
     - Monthly virtual number rental: ~₹500 - ₹1,000/month.
     - Sign up: [https://www.plivo.com/](https://www.plivo.com/)
  2. **Option B: Exotel (Local Indian Enterprise Champion)**:
     - Established connections with Airtel, Tata, and Jio.
     - Requires business KYC (Company PAN/GSTIN).
     - Sign up: [https://exotel.com/](https://exotel.com/)
* **Environment variables needed**:
  ```env
  TELEPHONY_PROVIDER=plivo # or exotel
  PLIVO_AUTH_ID=your_auth_id
  PLIVO_AUTH_TOKEN=your_auth_token
  PLIVO_PHONE_NUMBER=+91xxxxxxxxxx
  ```

---

### C. Communication & Notification Services

#### 5. Resend (Transactional Email)
* **Why it is needed**: To send:
  - Password reset links.
  - "New Lead Captured!" instant notification emails to business owners.
  - Call summaries and appointment confirmations.
* **Pricing**: Free tier includes **3,000 emails/month** (100 emails/day). Paid plans start at $20/month.
* **Where to get it**: [https://resend.com/](https://resend.com/) ➔ Verify your custom domain (`nimmiai.in`) and create an API key.
* **Environment variables needed**:
  ```env
  RESEND_API_KEY=re_...
  EMAIL_FROM=notifications@nimmiai.in
  ```

---

### D. Billing & Financial Activation

#### 6. Razorpay (Live Production Activation)
* **Current status in your codebase**: You already have Razorpay integrated in [`backend/payments.py`](file:///c:/Users/karth/.gemini/antigravity/scratch/nimmi-ai/backend/payments.py), but it requires Live Key activation to collect real INR.
* **What you need to complete**:
  1. Log in to [https://dashboard.razorpay.com/](https://dashboard.razorpay.com/).
  2. Submit your business KYC (Bank Account, PAN card, GSTIN or Business registration).
  3. Once approved, switch from **Test Mode** to **Live Mode**.
  4. Copy **Live Key ID** and **Live Key Secret** into production `.env`.
* **Environment variables needed**:
  ```env
  RAZORPAY_KEY_ID=rzp_live_...
  RAZORPAY_KEY_SECRET=your_live_secret
  RAZORPAY_WEBHOOK_SECRET=your_live_webhook_secret
  ```

---

## 3. Documents & Legal Requirements Required from Your End

To activate Indian telephony (Exotel/Plivo) and live Indian payment gateways (Razorpay), Indian telecom and financial regulations (TRAI & RBI) require specific legal documentation:

### Checklist of Documents to Have Ready:

1. **Business Identity**:
   - **Entity Type**: Sole Proprietorship, LLP, or Private Limited Company.
   - **PAN Card**: Personal PAN (if Proprietorship) or Company PAN (if LLP/Pvt Ltd).
   - **GSTIN Certificate**: Highly recommended (saves 18% GST via input tax credit and required by enterprise telecom providers).
   - **Udyam / MSME Registration Certificate**: Free to get online within 24 hours at [udyamregistration.gov.in](https://udyamregistration.gov.in/).
2. **Banking Verification**:
   - Cancelled cheque or 3-month bank statement of the current business account (for Razorpay daily payouts).
3. **TRAI DLT Portal Registration (Required for outbound phone calls & SMS)**:
   - To send SMS alerts or make commercial calls in India, register your business as a **Principal Entity (PE)** on any telecom operator's DLT portal (e.g., [Jio DLT](https://trueconnect.jio.com/) or [Airtel DLT](https://www.airtel.in/business/commercial-communication)).
   - **DLT Registration Fee**: One-time ~₹5,900 (inclusive of GST).
4. **Domain & Website Compliance Pages**:
   - To get Razorpay Live approval, your website ([`nimmiai.in`](https://nimmiai.in)) must publicly show:
     - **Terms & Conditions**
     - **Privacy Policy** (incorporating DPDP Act disclosures)
     - **Refund & Cancellation Policy**
     - **Contact Us** page with a physical address, support email, and phone number.

---

## 4. Total Budget & Initial Capital Requirement

| Item | Type | Upfront One-Time Cost | Monthly Recurring Cost |
| :--- | :--- | :--- | :--- |
| **Domain Registration (`.in` or `.com`)** | Annual | ~₹800 | ~₹70 / mo (amortized) |
| **Sarvam AI (Speech Models)** | Usage | ₹0 (includes ₹1,000 free credit) | ~₹500 - ₹1,500 / mo |
| **Groq Cloud (Fast LLM)** | Usage | ₹0 (Free tier) | ~₹0 - ₹200 / mo |
| **LiveKit Cloud (WebRTC)** | Usage | ₹0 (Free 50GB tier) | ~₹0 / mo initially |
| **Supabase + Pinecone** | Usage | ₹0 (Free tiers active) | ~₹0 / mo initially |
| **Cloud Hosting (Railway / VPS)** | Monthly | ₹0 | ~₹500 - ₹1,800 / mo |
| **Resend (Email Alerts)** | Monthly | ₹0 (Free 3,000 emails/mo) | ~₹0 / mo |
| **Razorpay Gateway** | Setup | ₹0 Setup Fee | 2% per transaction |
| **DLT Telecom Registration (Optional Phase 2)** | One-Time | ~₹5,900 | ₹0 |
| **Virtual Phone Number DID (Optional Phase 2)** | Monthly | ~₹1,000 setup | ~₹500 - ₹1,000 / mo |
| **TOTAL TO GET STARTED (Phase 1)** | — | **~₹1,000 - ₹2,000** | **~₹1,500 - ₹3,500 / month** |

> **Key takeaway**: You do **not** need a large capital outlay. You can build, test, and run your first 3 browser-voice + chatbot pilots for **less than ₹3,000 total out-of-pocket spend**.

---

## 5. Step-by-Step Implementation Sequence

### Step 1: Immediate Actions You Should Take Today
1. **Sign up on Sarvam AI**:
   - Visit [sarvam.ai](https://www.sarvam.ai/), create an account, generate an API Key, and claim the ₹1,000 test credits.
2. **Sign up on LiveKit Cloud**:
   - Visit [cloud.livekit.io](https://cloud.livekit.io/), create a free project, and copy your `LIVEKIT_URL`, `API_KEY`, and `SECRET`.
3. **Sign up on Groq Cloud**:
   - Visit [console.groq.com](https://console.groq.com/), create an API key for ultra-low latency Llama 3.3 inference.
4. **Sign up on Resend**:
   - Visit [resend.com](https://resend.com/), generate an API key for transactional emails.
5. **Activate Razorpay Live Mode**:
   - Upload business KYC documents to Razorpay to allow real credit/debit card and UPI payments.

### Step 2: What I (the AI Developer) Will Build Once Keys Are Ready
1. **LiveKit Voice Pipeline**: Add the Python LiveKit voice worker connecting Sarvam STT, Gemini/Groq LLM, and Sarvam TTS.
2. **Browser Voice Widget**: Add a "Talk to Voice Assistant" audio button in the Next.js widget and dashboard so clients can talk directly to their bot through their computer/phone microphone.
3. **Voice Usage & Billing Metering**: Update [`models.py`](file:///c:/Users/karth/.gemini/antigravity/scratch/nimmi-ai/backend/models.py) and [`payments.py`](file:///c:/Users/karth/.gemini/antigravity/scratch/nimmi-ai/backend/payments.py) to track voice minutes and sell prepaid minute recharge packs.
4. **CRM & Lead Alerts**: Automatically trigger an email via Resend and WhatsApp webhook whenever a visitor leaves contact information.
5. **Telephony Bridge (Phase 2)**: Plug in the Plivo/Exotel SIP trunk to route incoming and outgoing mobile phone calls to the LiveKit voice agent.

---

## 6. Master Environment Configuration (`.env.production` Template)

Once you have gathered the keys above, your backend environment file will look like this:

```env
# --- Supabase & Database ---
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
DATABASE_URL=postgresql+asyncpg://postgres:password@host:5432/postgres

# --- Pinecone Vector RAG ---
PINECONE_API_KEY=your_pinecone_key
PINECONE_INDEX_NAME=nimmi-knowledge-base

# --- LLM Providers ---
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key

# --- Speech AI (Sarvam AI) ---
SARVAM_API_KEY=your_sarvam_api_key

# --- WebRTC Media Streaming (LiveKit) ---
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_livekit_key
LIVEKIT_API_SECRET=your_livekit_secret

# --- Telephony (Phase 2) ---
PLIVO_AUTH_ID=your_plivo_auth_id
PLIVO_AUTH_TOKEN=your_plivo_auth_token
PLIVO_PHONE_NUMBER=+91xxxxxxxxxx

# --- Payments (Razorpay Live) ---
RAZORPAY_KEY_ID=rzp_live_...
RAZORPAY_KEY_SECRET=your_razorpay_secret
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret

# --- Email Notifications ---
RESEND_API_KEY=re_...
EMAIL_FROM=notifications@nimmiai.in

# --- App Settings ---
BACKEND_URL=https://api.nimmiai.in
DASHBOARD_URL=https://app.nimmiai.in
LOCAL_DEV=false
PORT=8000
```
