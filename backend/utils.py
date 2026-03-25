import os
import io
from PyPDF2 import PdfReader
import google.generativeai as genai
from google.generativeai.types import RequestOptions
from dotenv import load_dotenv

load_dotenv()

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
            "gemini-3-flash-preview": "gemini-2.0-flash",
            "gemini-2.0-flash-001": "gemini-2.0-flash",
            "gemini-1.5-pro": "gemini-1.5-pro", # Standard names
            "gemini-1.5-flash": "gemini-1.5-flash",
        }
        requested_model = (model_name or "gemini-2.0-flash").replace("models/", "")
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
