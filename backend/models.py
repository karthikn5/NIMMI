from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.sql import func
import uuid
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    password_hash = Column(String, nullable=True)
    subscription_tier = Column(String, default="Free")
    stripe_customer_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

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
    ai_model = Column(String, default="gemini-2.0-flash")
    ai_api_key = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    export_unlocked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Conversation(Base):
    __tablename__ = "conversations"
    conversation_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bot_id = Column(String(36), ForeignKey("bots.bot_id", ondelete="CASCADE"))
    visitor_session_id = Column(String, nullable=False)
    captured_data = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Message(Base):
    __tablename__ = "messages"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("conversations.conversation_id", ondelete="CASCADE"))
    role = Column(String, nullable=False) # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
