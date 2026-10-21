from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, JSON, Integer, Float, UniqueConstraint
from sqlalchemy.sql import func
import uuid
from datetime import datetime, timezone
from database import Base
from secretbox import EncryptedText  # secrets are stored encrypted at rest

class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    password_hash = Column(String, nullable=True)
    reset_token = Column(String, nullable=True)
    reset_token_expires = Column(DateTime(timezone=True), nullable=True)
    subscription_tier = Column(String, default="Free")
    stripe_customer_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    tokens_valid_after = Column(DateTime(timezone=True), nullable=True)  # sessions issued earlier are signed out

class Bot(Base):
    __tablename__ = "bots"
    bot_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    bot_name = Column(String, nullable=False)
    system_prompt = Column(Text, default="You are a helpful assistant.")
    visual_config = Column(JSON, default={"color": "#3b82f6", "logo_url": "", "position": "right"})
    flow_data = Column(JSON, default={"nodes": [], "edges": []})
    knowledge_base = Column(Text, nullable=True)
    ai_provider = Column(String, default="google") # google, openai, groq
    ai_model = Column(String, default="gemini-3-flash-preview")
    ai_api_key = Column(EncryptedText, nullable=True)
    behaviour = Column(JSON, nullable=True)  # reply settings from the builder; see behaviour.py
    is_active = Column(Boolean, default=True)
    export_unlocked = Column(Boolean, default=False)
    is_exported = Column(Boolean, default=False)
    exported_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Conversation(Base):
    __tablename__ = "conversations"
    conversation_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bot_id = Column(String(36), ForeignKey("bots.bot_id", ondelete="CASCADE"))
    visitor_session_id = Column(String, nullable=False)
    captured_data = Column(JSON, default={})
    handoff_requested = Column(Boolean, default=False)
    handoff_status = Column(String, default="ai") # ai, pending, human
    agent_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    current_node_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Message(Base):
    __tablename__ = "messages"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("conversations.conversation_id", ondelete="CASCADE"))
    role = Column(String, nullable=False) # 'user', 'assistant', or 'note' (internal, team only)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    author_id = Column(String(36), nullable=True)  # who wrote a note or an agent reply

class UserUsage(Base):
    __tablename__ = "user_usage"
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    total_credits = Column(Integer, default=1)
    used_credits = Column(Integer, default=0)

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    bot_id = Column(String(36), ForeignKey("bots.bot_id", ondelete="CASCADE"), nullable=True)
    plan_name = Column(String, nullable=False) # 1 Month, 6 Months, 12 Months
    credits_granted = Column(Integer, default=1)
    price_paid = Column(Integer, nullable=False)
    start_date = Column(DateTime(timezone=True), server_default=func.now())
    end_date = Column(DateTime(timezone=True), nullable=False)
    auto_renewal = Column(Boolean, default=True)
    razorpay_subscription_id = Column(String, nullable=True)
    razorpay_order_id = Column(String, nullable=True)
    status = Column(String, default="active") # active, expired, cancelled

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    bot_id = Column(String(36), ForeignKey("bots.bot_id", ondelete="CASCADE"), nullable=True)
    amount = Column(Integer, nullable=False)
    currency = Column(String, default="INR")
    razorpay_order_id = Column(String, nullable=True)
    razorpay_payment_id = Column(String, nullable=True)
    status = Column(String, default="pending") # pending, success, failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ─── Teams (agency workspaces) ───────────────────────────────────
class TeamMember(Base):
    """A person invited into another user's workspace."""
    __tablename__ = "team_members"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    member_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    email = Column(String, nullable=False)
    role = Column(String, default="agent")  # admin, agent
    status = Column(String, default="invited")  # invited, active
    invite_token = Column(String, nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ─── Voice ───────────────────────────────────────────────────────
class VoiceAgent(Base):
    """Voice settings for a bot. One row per bot that has voice configured."""
    __tablename__ = "voice_agents"
    bot_id = Column(String(36), ForeignKey("bots.bot_id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    enabled = Column(Boolean, default=False)
    language = Column(String, default="en-IN")
    understand_code_mixed = Column(Boolean, default=True)
    voice_id = Column(String, nullable=True)
    speaking_rate = Column(Float, default=1.0)
    assistant_name = Column(String, default="Nimmi")
    company_name = Column(String, default="")
    greeting = Column(String, default="How can I help you today?")
    allow_interruptions = Column(Boolean, default=True)
    silence_timeout_sec = Column(Integer, default=8)
    max_call_minutes = Column(Integer, default=10)
    transfer_enabled = Column(Boolean, default=False)
    transfer_number = Column(String, default="")
    transfer_when = Column(Text, default="The caller asks to speak to a person.")
    end_call_phrases = Column(JSON, default=lambda: ["that's all", "bye"])
    tested_at = Column(DateTime(timezone=True), nullable=True)
    # What the call is for, and what to find out (post-call analysis). Fields: [{key, label, type, description, choices, required}]
    call_goal = Column(Text, nullable=True)
    collect_fields = Column(JSON, nullable=True)
    # Realism
    ambience = Column(String, nullable=True)            # none, office, call_center, cafe, street, static
    ambience_volume = Column(String, nullable=True)     # low, medium, high
    silence_reminders = Column(Integer, nullable=True)  # "Are you still there?" prompts before hanging up (0-3)
    pronunciations = Column(JSON, nullable=True)        # [{word, say}] applied to speech only
    # Outbound and hand-off
    voicemail_action = Column(String, nullable=True)    # off, hangup, leave_message (Twilio only)
    voicemail_message = Column(Text, nullable=True)
    transfer_mode = Column(String, nullable=True)       # cold, warm (warm: staff hear a summary first)


class PhoneNumber(Base):
    __tablename__ = "phone_numbers"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    number = Column(String, nullable=False)  # display form, e.g. +91 44 4567 8120
    e164 = Column(String, nullable=True, index=True)  # +914445678120, set once issued
    kind = Column(String, default="landline")
    city = Column(String, default="")
    status = Column(String, default="pending_kyc")  # pending_kyc, provisioning, active
    bot_id = Column(String(36), ForeignKey("bots.bot_id", ondelete="SET NULL"), nullable=True)
    monthly_fee = Column(Integer, default=0)
    provider = Column(String, default="exotel")
    kyc_documents = Column(JSON, default=lambda: [])
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Self-serve numbers (Twilio): the provider's id, country, and the monthly rental cycle.
    provider_sid = Column(String, nullable=True)
    country = Column(String, nullable=True)  # ISO code, e.g. US
    next_charge_at = Column(DateTime(timezone=True), nullable=True)
    suspended_at = Column(DateTime(timezone=True), nullable=True)  # status "suspended" when rent couldn't be paid
    # Numbers from the customer's own Twilio or Exotel account (bring your own number). None = Nimmi's account.
    account_id = Column(String(36), ForeignKey("telephony_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    previous_voice_url = Column(String, nullable=True)  # their webhook before we pointed it here; restored on removal
    replaced_at = Column(DateTime(timezone=True), nullable=True)  # last swap for a new number (once per billing period)


class TelephonyAccount(Base):
    """A customer's own Twilio or Exotel account, used to answer and place calls from their numbers."""
    __tablename__ = "telephony_accounts"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider = Column(String, nullable=False)  # twilio, exotel
    label = Column(String, default="")
    account_sid = Column(String, nullable=False)
    secrets = Column(Text, nullable=False)  # encrypted JSON: twilio {token}; exotel {api_key, api_token}
    subdomain = Column(String, nullable=True)  # exotel: api.exotel.com or api.in.exotel.com
    app_id = Column(String, nullable=True)  # exotel: the flow (app) that runs the voicebot
    webhook_token = Column(String, nullable=False, unique=True, index=True)  # in this account's webhook URLs
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Balance(Base):
    """Prepaid Nimmi balance in paise, used for number rental."""
    __tablename__ = "balances"
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    balance_paise = Column(Integer, default=0, nullable=False)


class BalanceEntry(Base):
    """Ledger of every change to a balance. `ref` is unique so a charge or top-up applies once."""
    __tablename__ = "balance_entries"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount_paise = Column(Integer, nullable=False)  # + top-up / refund, - charge
    kind = Column(String, nullable=False)  # topup, number_rental, refund, adjustment
    ref = Column(String, unique=True, nullable=False)
    note = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CallbackSettings(Base):
    __tablename__ = "callback_settings"
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    enabled = Column(Boolean, default=False)
    delay = Column(String, default="1m")  # immediate, 1m, 5m, 15m
    window_start = Column(String, default="09:00")
    window_end = Column(String, default="21:00")
    max_attempts = Column(Integer, default=2)
    from_number_id = Column(String(36), nullable=True)


class ComplianceSettings(Base):
    __tablename__ = "compliance_settings"
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    record_calls = Column(Boolean, default=True)
    retention_days = Column(Integer, default=90)
    opt_out_phrases = Column(JSON, default=lambda: ["don't call me", "do not call", "stop calling", "remove my number"])


class DncEntry(Base):
    __tablename__ = "dnc_entries"
    __table_args__ = (UniqueConstraint("user_id", "e164", name="uq_dnc_user_number"),)
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    e164 = Column(String, nullable=False)
    reason = Column(String, default="manual")  # caller_request, manual, imported
    added_at = Column(DateTime(timezone=True), server_default=func.now())


class CallLog(Base):
    __tablename__ = "call_logs"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    bot_id = Column(String(36), ForeignKey("bots.bot_id", ondelete="SET NULL"), nullable=True, index=True)
    direction = Column(String, default="inbound")  # inbound, outbound
    channel = Column(String, default="phone")  # phone, browser
    caller_e164 = Column(String, nullable=True, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_sec = Column(Integer, default=0)
    billed_minutes = Column(Integer, default=0)
    outcome = Column(String, default="answered")
    language = Column(String, default="en-IN")
    summary = Column(Text, nullable=True)
    captured = Column(JSON, default=lambda: {})
    transcript = Column(JSON, default=lambda: [])
    recording_path = Column(String, nullable=True)
    consent_source = Column(String, nullable=True)
    provider_call_id = Column(String, nullable=True, index=True)
    successful = Column(Boolean, nullable=True)   # did the call reach the agent's goal
    sentiment = Column(String, nullable=True)     # positive, neutral, negative
    campaign_id = Column(String(36), nullable=True, index=True)


class Campaign(Base):
    """An outbound calling list: people who agreed to be called, rung by one assistant."""
    __tablename__ = "campaigns"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    bot_id = Column(String(36), ForeignKey("bots.bot_id", ondelete="CASCADE"))
    name = Column(String, nullable=False)
    purpose = Column(Text, default="")              # why we're calling; supports {{variables}}
    status = Column(String, default="running")       # running, paused, completed, cancelled
    from_number_id = Column(String(36), nullable=True)
    window_start = Column(String, default="10:00")   # IST
    window_end = Column(String, default="19:00")
    max_attempts = Column(Integer, default=2)
    concurrency = Column(Integer, default=1)
    consent_note = Column(Text, nullable=True)       # who confirmed consent, and when
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class CallbackJob(Base):
    """A consented callback request waiting to be dialled."""
    __tablename__ = "callback_jobs"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    bot_id = Column(String(36), ForeignKey("bots.bot_id", ondelete="CASCADE"))
    e164 = Column(String, nullable=False)
    name = Column(String, nullable=True)
    consent_source = Column(String, nullable=False)
    consent_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String, default="queued", index=True)  # queued, calling, done, failed, cancelled
    attempts = Column(Integer, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_error = Column(String, nullable=True)
    call_id = Column(String(36), nullable=True)
    provider_call_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    campaign_id = Column(String(36), nullable=True, index=True)
    variables = Column(JSON, nullable=True)  # per-contact values for {{placeholders}}, from the campaign list


class VoiceWallet(Base):
    """Voice minutes: plan minutes reset each cycle; top-up minutes carry over."""
    __tablename__ = "voice_wallets"
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    plan_minutes = Column(Integer, default=0)
    plan_minutes_used = Column(Integer, default=0)
    topup_minutes = Column(Integer, default=0)
    cycle_end = Column(DateTime(timezone=True), nullable=True)


class VoiceTopup(Base):
    __tablename__ = "voice_topups"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    pack_id = Column(String, nullable=False)
    minutes = Column(Integer, nullable=False)
    amount = Column(Integer, nullable=False)  # INR, excl. GST
    razorpay_order_id = Column(String, unique=True, nullable=False)
    razorpay_payment_id = Column(String, unique=True, nullable=True)
    status = Column(String, default="pending")  # pending, paid
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ─── Integrations & notifications ────────────────────────────────
class IntegrationSettings(Base):
    __tablename__ = "integration_settings"
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    email_alerts = Column(Boolean, default=True)
    alert_email = Column(String, nullable=True)
    whatsapp_enabled = Column(Boolean, default=False)
    whatsapp_template = Column(String, nullable=True)
    whatsapp_language = Column(String, default="en")
    webhook_url = Column(String, nullable=True)
    webhook_secret = Column(EncryptedText, nullable=True)
    leadsquared_enabled = Column(Boolean, default=False)
    leadsquared_host = Column(String, nullable=True)
    leadsquared_access_key = Column(EncryptedText, nullable=True)
    leadsquared_secret_key = Column(EncryptedText, nullable=True)
    # WhatsApp 2-Way AI Chatbot
    whatsapp_chat_enabled = Column(Boolean, default=False, nullable=True)
    whatsapp_bot_id = Column(String(36), ForeignKey("bots.bot_id", ondelete="SET NULL"), nullable=True)
    whatsapp_phone_number_id = Column(String, nullable=True)
    whatsapp_access_token = Column(EncryptedText, nullable=True)
    whatsapp_verify_token = Column(String, nullable=True)
    whatsapp_business_account_id = Column(String, nullable=True)
    # Email: which team alerts go out, and automatic emails to customers
    alert_calls = Column(Boolean, nullable=True)        # call summaries (None = on, the original behaviour)
    alert_handoffs = Column(Boolean, nullable=True)     # "a customer asked for a person"
    sender_name = Column(String, nullable=True)         # shown as the From name on customer emails
    reply_to = Column(String, nullable=True)            # where customers' replies go
    email_automations = Column(JSON, nullable=True)     # {"chat_lead": {...}, "call_lead": {...}}


class EmailJob(Base):
    """An automatic email to a customer, waiting for its send time. One per (kind, ref_id)."""
    __tablename__ = "email_jobs"
    __table_args__ = (UniqueConstraint("kind", "ref_id", name="uq_email_job"),)
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind = Column(String, nullable=False)        # automation (with "#2"/"#3" for follow-ups) or "broadcast:<id>"
    ref_id = Column(String(36), nullable=False)  # conversation, call or callback id; for bulk email a hash of the address
    to_email = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    send_at = Column(DateTime(timezone=True), index=True)
    status = Column(String, default="queued", index=True)  # queued, sent, failed, cancelled
    error = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    automation = Column(String, nullable=True)  # chat_lead, call_lead, goal_met, call_missed, handoff_done
    step = Column(Integer, nullable=True)  # 1, 2, 3 in a sequence
    sent_at = Column(DateTime(timezone=True), nullable=True)
    broadcast_id = Column(String(36), nullable=True, index=True)  # set for bulk emails


class EmailBroadcast(Base):
    """A bulk email to a group of leads; each recipient is an EmailJob with this broadcast_id."""
    __tablename__ = "email_broadcasts"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    audience = Column(JSON, default=dict)  # {source, days, hot_only}
    recipients = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EmailUnsubscribe(Base):
    """Customers who asked a workspace to stop emailing them."""
    __tablename__ = "email_unsubscribes"
    __table_args__ = (UniqueConstraint("user_id", "email", name="uq_email_unsub"),)
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    email = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NotificationLog(Base):
    """One row per notification, so the same lead never alerts twice."""
    __tablename__ = "notification_logs"
    __table_args__ = (UniqueConstraint("kind", "ref_id", name="uq_notification_kind_ref"),)
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind = Column(String, nullable=False)  # lead_email, call_email, whatsapp, webhook, leadsquared
    ref_id = Column(String, nullable=False)
    status = Column(String, default="sent")  # sent, failed, skipped
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WorkspaceSettings(Base):
    """Business hours and how assistants hand over to people, per workspace."""
    __tablename__ = "workspace_settings"
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    business_hours = Column(JSON, nullable=True)   # {"enabled", "days": {"mon": {"open", "from", "to"}}, "holidays", "away_message"}
    escalate_upset = Column(Boolean, nullable=True)  # hand upset customers to a person (None = on)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class KnowledgeGap(Base):
    """
    A question an assistant couldn't answer (status "open"), grouped by wording.
    Once the business writes an answer (status "answered"), the assistant uses it from then on.
    """
    __tablename__ = "knowledge_gaps"
    __table_args__ = (UniqueConstraint("bot_id", "normalized", name="uq_gap_bot_question"),)
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bot_id = Column(String(36), ForeignKey("bots.bot_id", ondelete="CASCADE"), index=True)
    question = Column(Text, nullable=False)
    normalized = Column(String(300), nullable=False)
    answer = Column(Text, nullable=True)
    status = Column(String, default="open", index=True)  # open, answered, dismissed
    count = Column(Integer, default=1)
    channel = Column(String, nullable=True)  # chat, whatsapp, voice, manual
    last_conversation_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_asked_at = Column(DateTime(timezone=True), server_default=func.now())


class SavedReply(Base):
    """Answers a team reuses in Live chat."""
    __tablename__ = "saved_replies"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title = Column(String(80), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DeletedItem(Base):
    """Something a workspace deleted, kept for 30 days so it can be restored (see recycle.py)."""
    __tablename__ = "deleted_items"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)  # the workspace
    kind = Column(String, nullable=False)  # bot
    ref_id = Column(String(36), nullable=False, index=True)
    label = Column(String, nullable=True)
    deleted_by = Column(String(36), nullable=True)
    payload = Column(JSON, nullable=False)
    deleted_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)


class Site(Base):
    """A website the workspace publishes on Nimmi (static files), at <slug>.<SITES_DOMAIN> and optionally its own domain."""
    __tablename__ = "sites"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)  # the workspace
    name = Column(String(80), nullable=False)
    slug = Column(String(63), unique=True, nullable=False, index=True)
    current_deploy_id = Column(String(36), nullable=True)  # what visitors see; switched only once a deploy is complete
    bot_id = Column(String(36), ForeignKey("bots.bot_id", ondelete="SET NULL"), nullable=True)  # assistant added to every page
    spa = Column(String(8), default="auto")  # auto | on | off: unknown paths show index.html (single-page apps)
    # Git: the repository to publish from, and a secret deploy-hook link (e.g. a GitHub webhook) to publish on push.
    git_url = Column(String(300), nullable=True)
    git_branch = Column(String(100), nullable=True)
    git_folder = Column(String(200), nullable=True)
    git_token = Column(EncryptedText, nullable=True)  # for private repositories
    hook_secret = Column(String(64), nullable=True)
    # Custom domain (paid plans): verified by a TXT record, served once the edge has its certificate.
    custom_domain = Column(String(253), unique=True, nullable=True)
    domain_status = Column(String(20), nullable=True)  # pending | issuing | active | failed
    domain_token = Column(String(64), nullable=True)
    domain_provider_id = Column(String(100), nullable=True)  # Cloudflare custom hostname id
    domain_error = Column(String(300), nullable=True)
    domain_checked_at = Column(DateTime(timezone=True), nullable=True)
    domain_added_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default="active")  # active | blocked (abuse)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)  # kept 30 days, then removed


class SiteDeploy(Base):
    """One published version of a site. Files are stored once per site by content hash (see sites/storage.py)."""
    __tablename__ = "site_deploys"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id = Column(String(36), ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    status = Column(String(20), default="building")  # building | ready | failed
    source = Column(String(20), nullable=False)  # upload | git | hook
    files = Column(JSON, nullable=True)  # {"path/in/site.html": ["sha256", size]}
    file_count = Column(Integer, default=0)
    total_bytes = Column(Integer, default=0)
    spa = Column(Boolean, default=False)  # detected: one HTML page that routes itself
    commit_sha = Column(String(64), nullable=True)
    commit_message = Column(String(300), nullable=True)
    note = Column(String(300), nullable=True)  # e.g. "Skipped 3 files (.env, node_modules)"
    error = Column(String(500), nullable=True)
    created_by = Column(String(36), nullable=True)
    # Set here, to the microsecond: deploys started in the same second still sort in order.
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime(timezone=True), nullable=True)
