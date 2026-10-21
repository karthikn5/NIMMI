import io
import logging
import os

from dotenv import load_dotenv
from pypdf import PdfReader  # maintained successor of PyPDF2

import ai

load_dotenv()

logger = logging.getLogger(__name__)

# Used by the voice agent (voice/llm.py), which still calls Gemini through the older SDK.
SAFETY_SETTINGS = [{"category": c, "threshold": "BLOCK_NONE"} for c in (
    "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT")]


def _system(system_prompt: str, context: str) -> str:
    return f"{system_prompt.strip()}\n\n# Business knowledge\n{(context or '').strip()}" if context else system_prompt


def generate_ai_response(system_prompt, context, user_query, provider="google", model_name=None, api_key=None,
                         is_system_use=False, history=None):
    """One answer (WhatsApp, flow AI steps). Never raises; visitors get a polite message if the AI is down."""
    messages = list(history or []) + [{"role": "user", "content": user_query}]
    try:
        return ai.chat(_system(system_prompt, context), messages, provider=provider or "google", model=model_name, api_key=api_key)
    except ai.AIError as e:
        logger.error(f"AI answer failed: {e}")
        return ai.SORRY


def generate_ai_response_stream(system_prompt, context, user_query, history=None, provider="google", model_name=None, api_key=None):
    """The same, streamed in pieces."""
    messages = list(history or []) + [{"role": "user", "content": user_query}]
    try:
        yield from ai.chat_stream(_system(system_prompt, context), messages, provider=provider or "google",
                                  model=model_name, api_key=api_key)
    except ai.AIError as e:
        logger.error(f"AI answer failed: {e}")
        yield ai.SORRY


MAX_PDF_PAGES = 400
MAX_TEXT_CHARS = 2_000_000


def extract_text_from_pdf(file_stream) -> str:
    """Text of a PDF, capped in pages and characters so a crafted file can't tie up the server."""
    try:
        reader = PdfReader(file_stream)
        parts, size = [], 0
        for page in reader.pages[:MAX_PDF_PAGES]:
            chunk = (page.extract_text() or "") + "\n"
            parts.append(chunk)
            size += len(chunk)
            if size > MAX_TEXT_CHARS:
                break
        return "".join(parts)[:MAX_TEXT_CHARS]
    except Exception:
        return "Error"

def extract_text_from_txt(file_stream) -> str:
    try:
        content = file_stream.read(MAX_TEXT_CHARS * 4)
        return content.decode("utf-8", errors="replace")[:MAX_TEXT_CHARS] if isinstance(content, bytes) else content[:MAX_TEXT_CHARS]
    except Exception:
        return "Error"

class FlowEngine:
    @staticmethod
    def get_next_node(flow_data, current_node_id):
        nodes = flow_data.get("nodes", [])
        edges = flow_data.get("edges", [])
        
        # If no current node, start at entry point
        if not current_node_id:
            start_node = next((n for n in nodes if n["type"] == "start"), None)
            if not start_node: return None
            current_node_id = start_node["id"]
            
        # Find edge from current node
        edge = next((e for e in edges if e["source"] == current_node_id), None)
        if not edge: return None
        
        target_node = next((n for n in nodes if n["id"] == edge["target"]), None)
        return target_node

    @staticmethod
    def process(flow_data, current_node_id):
        """
        Executes the flow until it reaches a node that requires user input or a handover.
        Returns a list of messages to send and the new node_id.
        """
        messages = []
        handoff_triggered = False
        
        node = FlowEngine.get_next_node(flow_data, current_node_id)
        
        while node:
            current_node_id = node["id"]
            node_type = node.get("type")
            node_data = node.get("data", {})
            
            if node_type == "message":
                messages.append(node_data.get("label", "Message"))
                # Keep going to next node
            elif node_type == "handover":
                # This is the actual logic node
                handoff_triggered = True
                messages.append(node_data.get("message", "I've notified a human agent."))
                break
            elif node_type == "textInput" or node_type == "emailInput":
                messages.append(node_data.get("label", "Please enter input:"))
                # Stop here and wait for user
                break
            
            # Find next node
            node = FlowEngine.get_next_node(flow_data, current_node_id)
            if not node: break
            
        return messages, current_node_id, handoff_triggered
