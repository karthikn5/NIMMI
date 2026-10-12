# Research Review: Voice AI Plan (fact-check, 11 Oct 2026)

A review of `research.md` and `requirement.md` against current provider docs and Indian regulations. The direction holds up: inbound answering plus consented callbacks for education, clinics and real estate, with Sarvam for Indian speech. The changes below are corrections to numbers and rules, and none of them change that strategy.

---

## 1. Corrections that change the numbers

### TTS cost is about 10x higher than stated
- Sarvam prices Bulbul at **₹3 per 1,000 characters** (₹30 per 10k). The research uses the right rate but gets the wrong per-minute figure: 800 chars × ₹3/1000 = **₹2.40 per minute of speech**, not ₹0.24.
- The assistant speaks for roughly 40–50% of a call, so TTS costs about **₹1.0–1.3 per call-minute**.

**Revised cost per call-minute**

| Component | Research | Revised |
| :--- | :--- | :--- |
| Telephony | ₹0.40 | ₹0.40–0.60 |
| STT (Saaras, ₹30/hr) | ₹0.50 | ₹0.50 |
| LLM | ₹0.02 | ₹0.02–0.05 |
| TTS (Bulbul) | ₹0.24 | **₹1.00–1.30** |
| Media / hosting | ₹0.06 | ₹0.10+ (more if agents run on LiveKit Cloud beyond the free tier) |
| **Total** | **₹1.22** | **≈ ₹2.0–2.5+** |

**What this means**
- An overage price of ₹3.00–3.50/min leaves very little margin. Price overage and top-up packs at **₹4.50–5.50/min**. The UI's sample packs use ₹4.50–5.49 for this reason.
- Plan margins are still healthy. Growth (100 min) voice cost goes from ₹122 to about ₹250. Business (400 min) goes from ₹488 to about ₹1,000.
- You can cut TTS spend by caching fixed audio (the disclosure, greetings, common answers) and keeping replies short in the voice prompt.

### Model names and coverage
- Sarvam's API reference lists **Saaras v4** (default) and v3 for STT, and **Bulbul v3** (default), v4-flash and v2 for TTS. *(An earlier version of this review said v4 didn't exist; that was wrong.)* The code-mix mode used for Tanglish and Hinglish is documented for Saaras v3, so the voice engine defaults to `saaras:v3` and `bulbul:v3`; both are configurable with `SARVAM_STT_MODEL` and `SARVAM_TTS_MODEL`.
- **Bulbul v3 speaks 11 languages** (Hindi, Bengali, Tamil, Telugu, Gujarati, Kannada, Malayalam, Marathi, Punjabi, Odia, English). Saaras can *understand* 22 languages and has a code-mix mode. So an agent can listen to Tanglish or Hinglish but can only reply in those 11. The UI's language list is limited to them.
- **Gemini 2.0 Flash shut down on 1 June 2026**, and Gemini 2.5 Flash shuts down on 16 Oct 2026. The backend uses `-latest` aliases, so chat keeps working. For the voice pipeline, pin a current Flash model and re-measure latency; don't use the 2.0 figures.

### LiveKit free tier
- The Build plan includes **1,000 agent minutes and 5,000 WebRTC minutes per month**. It is a hard cap, and requests fail once it's used up. That is about 16 hours of agent conversation, enough for development and one small pilot. The research quotes the 50 GB bandwidth limit, but agent minutes are what will actually limit you.

---

## 2. Regulatory corrections

| Claim in research | Actual | Change made |
| :--- | :--- | :--- |
| 160-series numbers for service calls; "Dedicated DLT 160 number" in Enterprise plan | The **1600-series is only for BFSI** (entities regulated by RBI, SEBI, IRDAI or PFRDA) and government. Clinics, colleges and builders can't get one. | Remove it from the Enterprise plan. Use landline-series numbers, which are allowed for service and transactional calls only. |
| Sole proprietorship is enough for telephony | Plivo India accepts **only a Certificate of Incorporation plus a GST certificate**, and the business must be registered in India. A proprietorship can't rent Indian numbers there. | Incorporate (LLP or Pvt Ltd), or go with Exotel. The "Get a number" dialog states the document requirement up front. |
| Outbound "requested callback" | Cold calling is prohibited, and **explicit digital consent** is required before a commercial call. Plivo also requires call media to stay in India, with a default limit of 2 outbound calls per second. | Callbacks can only go to people who asked. The UI shows this as a locked rule, not a toggle, and each callback shows its consent source. |
| DPDP disclosures | DPDP Rules were notified on 14 Nov 2025. Notice, security, breach-reporting and retention duties apply from **13 May 2027**. | Build these now. Retention, erase-on-request and the do-not-call list are already on the Compliance screen. |

---

## 3. Architecture simplification for phone calls

Exotel's **Voicebot applet streams call audio over a bidirectional WebSocket** (8 kHz 16-bit PCM, base64 in JSON). Phone calls can therefore go Exotel → FastAPI WebSocket → STT/LLM/TTS, with no SIP trunk.

**As built:** the browser test call uses the same approach (16 kHz PCM over a WebSocket to FastAPI), so one call engine (`backend/voice/pipeline.py`) serves both. LiveKit isn't needed, which removes one vendor, one bill and the 1,000-minute free-tier cap. LiveKit stays an option later if you want WebRTC for an in-browser voice widget on customer sites with poor networks.

---

## 4. Voice API (implemented)

These endpoints are built in `backend/voice/router.py` and used by the screens under `/dashboard/voice`.

| Endpoint | Used by |
| :--- | :--- |
| `GET /api/voice/overview?user_id=` | Overview metrics, chart, minutes, setup |
| `GET /api/voice/agents?user_id=` · `GET/PUT /api/voice/agents/{bot_id}` | Agents list and settings |
| `GET /api/voice/voices` | Voice picker (`sample_url` enables Play) |
| `POST /api/voice/session` → `{ ws_path, token }`, then `WS /api/voice/ws/browser` | Browser test call |
| `WS /api/voice/ws/exotel/{secret}` | Phone calls (Exotel Voicebot applet) |
| `GET /api/voice/calls?user_id=` · `GET /api/voice/calls/{id}` | Calls list and detail |
| `GET /api/voice/numbers?user_id=` · `POST /api/voice/numbers` · `PATCH /api/voice/numbers/{id}` | Numbers and routing |
| `GET/PUT /api/voice/callbacks` | Lead callback settings |
| `GET/PUT /api/voice/compliance` | Recording, retention, opt-out phrases |
| `GET/POST /api/voice/dnc` · `DELETE /api/voice/dnc/{id}` | Do-not-call list |
| `POST /api/voice/erase` | Erase a caller's data |
| `GET /api/voice/packs` · `POST /api/payments/create-minutes-order` | Minute top-ups |

Shapes are defined in `dashboard/src/lib/voice/types.ts`.

---

### Sources
- [Sarvam API pricing](https://docs.sarvam.ai/api-reference-docs/pricing) · [Sarvam models](https://docs.sarvam.ai/api/getting-started/models) · [Bulbul](https://docs.sarvam.ai/api/models/bulbul)
- [Gemini 2.0 Flash deprecation](https://discuss.ai.google.dev/t/model-deprecations-and-replacements-gemini-flash-2-0/109757) · [2.0 Flash migration costs](https://tokencost.app/blog/gemini-2-0-flash-deprecated-migration-cost)
- [LiveKit pricing](https://livekit.com/pricing) · [LiveKit quotas](https://docs.livekit.io/deploy/admin/quotas-and-limits/)
- [TRAI 1600-series direction (PIB)](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2205350&reg=3&lang=1) · [1600-series explained](https://vinodkothari.com/2026/03/adopting-1600-number-series-preventive-measure-or-burden/)
- [Plivo India calling](https://docs.plivo.com/docs/voice/concepts/india-calling) · [Plivo domestic calling in India](https://support.plivo.com/hc/en-us/articles/16859884362265)
- [DPDP Rules 2025 timeline](https://ssrana.in/articles/meity-notifies-final-digital-personal-data-protection-rules-2025/)
- [Exotel Voicebot applet](https://developer.exotel.com/docs/agentstream/stream-voicebot-applet) · [Exotel AgentStream](https://developer.exotel.com/docs/agentstream/getting-started)
