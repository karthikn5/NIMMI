import os
import io
from PyPDF2 import PdfReader
import google.generativeai as genai
from google.generativeai.types import RequestOptions
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

import openai
from groq import Groq

# Initialize Clients (Resilient)
GEMINI_DEFAULT_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_DEFAULT_KEY = os.getenv("OPENAI_API_KEY")
GROQ_DEFAULT_KEY = os.getenv("GROQ_API_KEY")

try:
    if GEMINI_DEFAULT_KEY:
        # Using transport='rest' can bypass some gRPC-related 404/version issues
        genai.configure(api_key=GEMINI_DEFAULT_KEY, transport='rest')
except Exception as e:
    print(f"Warning: Gemini configuration failed: {e}")

def generate_ai_response(system_prompt, context, user_query, provider="google", model_name=None, api_key=None, is_system_use=False):
    # Truncate context
    MAX_CONTEXT_LENGTH = 30000 
    if len(context) > MAX_CONTEXT_LENGTH:
        context = context[:MAX_CONTEXT_LENGTH] + "...[truncated]"

    prompt = f"{system_prompt}\n\nContext:\n{context}\n\nUser Question: {user_query}\n\nAnswer:"
    
    if provider == "google":
        current_api_key = api_key or GEMINI_DEFAULT_KEY
        # Map invalid/old model names to valid ones
        model_mapping = {
            "gemini-2.0-flash-001": "gemini-2.0-flash",
            "gemini-1.5-pro": "gemini-1.5-pro", # Standard names
            "gemini-1.5-flash": "gemini-1.5-flash",
        }
        requested_model = (model_name or "gemini-3-flash-preview").replace("models/", "")
        primary_model = model_mapping.get(requested_model, requested_model)
        
        # Build fallback chain with free-tier models only
        models_to_try = [primary_model]
        if primary_model != "gemini-1.5-flash":
            models_to_try.append("gemini-1.5-flash")
            
        last_err = ""
        for m_name in models_to_try:
            # Try both with and without models/ prefix as some environments/versions differ
            possible_names = [m_name, f"models/{m_name}"]
            for full_name in possible_names:
                try:
                    print(f"DEBUG: Attempting Gemini call with model='{full_name}' (transport=rest)")
                    genai.configure(api_key=current_api_key, transport='rest')
                    model = genai.GenerativeModel(full_name)
                    response = model.generate_content(prompt)
                    return response.text
                except Exception as e:
                    last_err = str(e)
                    print(f"DEBUG: Gemini Model '{full_name}' failed: {last_err}")
                    # If it's a 404, we want to try the next name or model
                    if "404" not in last_err and "not found" not in last_err.lower():
                        # If it's a quota or auth error, don't just loop names
                        break 
                
        # If all failed for bot key, try system key as a last resort
        if current_api_key != GEMINI_DEFAULT_KEY:
            try:
                print("DEBUG: All bot-key models failed. Trying system key fallback...")
                genai.configure(api_key=GEMINI_DEFAULT_KEY, transport='rest')
                model = genai.GenerativeModel("gemini-1.5-flash")
                response = model.generate_content(prompt)
                return response.text
            except Exception as sys_e:
                print(f"DEBUG: System key fallback also failed: {sys_e}")
                last_err = f"Bot Key Error: {last_err} | System Key Error: {sys_e}"

        return f"Gemini API Error: {last_err[:200]}"

    elif provider == "openai":
        # ... (OpenAI handling)
        selected_model = model_name or "gpt-4o-mini"
        current_api_key = api_key or OPENAI_DEFAULT_KEY
        client = openai.OpenAI(api_key=current_api_key)
        response = client.chat.completions.create(
            model=selected_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context:\n{context}\n\nUser Question: {user_query}"}
            ]
        )
        return response.choices[0].message.content

    return "Error: AI Provider not supported."


def generate_ai_response_stream(system_prompt, context, user_query, history=None, provider="google", model_name=None, api_key=None):
    """
    Streaming version of generate_ai_response.
    Yields text chunks as they arrive from the AI model.
    """
    MAX_CONTEXT_LENGTH = 8000  
    if len(context) > MAX_CONTEXT_LENGTH:
        context = context[:MAX_CONTEXT_LENGTH] + "...[truncated]"

    # Format history for the prompt
    history_str = ""
    if history:
        for turn in history[-5:]: # Last 5 turns for context
            role = "User" if turn.get("role") == "user" else "Assistant"
            content = turn.get("content", "")
            history_str += f"{role}: {content}\n"

    prompt = f"""SYSTEM INSTRUCTIONS:
{system_prompt}

YOUR INTERNAL KNOWLEDGE (Use this to answer):
{context}

CONVERSATION HISTORY:
{history_str}
User: {user_query}
Assistant:"""

    if provider == "google":
        current_api_key = api_key or GEMINI_DEFAULT_KEY
        model_mapping = {
            "gemini-2.0-flash-001": "gemini-2.0-flash",
            "gemini-1.5-pro": "gemini-1.5-pro",
            "gemini-1.5-flash": "gemini-1.5-flash",
        }
        requested_model = (model_name or "gemini-3-flash-preview").replace("models/", "")
        primary_model = model_mapping.get(requested_model, requested_model)

        models_to_try = [primary_model]
        if primary_model != "gemini-1.5-flash":
            models_to_try.append("gemini-1.5-flash")

        for m_name in models_to_try:
            possible_names = [m_name, f"models/{m_name}"]
            for full_name in possible_names:
                try:
                    genai.configure(api_key=current_api_key, transport='rest')
                    model = genai.GenerativeModel(full_name)
                    response = model.generate_content(prompt, stream=True)
                    for chunk in response:
                        try:
                            if chunk.text:
                                logger.info(f"Yielding chunk: {len(chunk.text)} chars")
                                yield chunk.text
                        except Exception as chunk_err:
                            logger.warning(f"Error reading chunk text: {chunk_err}")
                            # Some chunks might not have text (e.g. finish reason or safety)
                            continue
                    return  # Successfully streamed
                except Exception as e:
                    logger.error(f"Gemini streaming error for {full_name}: {e}")
                    last_err = str(e)
                    if "404" not in last_err and "not found" not in last_err.lower():
                        break
                    continue

        # Fallback to system key
        if current_api_key != GEMINI_DEFAULT_KEY:
            try:
                logger.info("Attempting fallback with default Gemini key")
                genai.configure(api_key=GEMINI_DEFAULT_KEY, transport='rest')
                model = genai.GenerativeModel("gemini-1.5-flash")
                response = model.generate_content(prompt, stream=True)
                for chunk in response:
                    try:
                        if chunk.text:
                            yield chunk.text
                    except Exception:
                        continue
                return
            except Exception as fallback_err:
                logger.error(f"Fallback Gemini streaming error: {fallback_err}")

        yield "Sorry, I'm having trouble responding right now. Please try again."

    elif provider == "openai":
        selected_model = model_name or "gpt-4o-mini"
        current_api_key = api_key or OPENAI_DEFAULT_KEY
        client = openai.OpenAI(api_key=current_api_key)
        response = client.chat.completions.create(
            model=selected_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context:\n{context}\n\nUser Question: {user_query}"}
            ],
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    else:
        yield "Error: AI Provider not supported."


def extract_text_from_pdf(file_stream) -> str:
    try:
        reader = PdfReader(file_stream)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except: return "Error"

def extract_text_from_txt(file_stream) -> str:
    try:
        content = file_stream.read()
        return content.decode("utf-8") if isinstance(content, bytes) else content
    except: return "Error"
