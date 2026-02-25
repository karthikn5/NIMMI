import os
import io
from PyPDF2 import PdfReader
import google.generativeai as genai
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
        genai.configure(api_key=GEMINI_DEFAULT_KEY)
except Exception as e:
    print(f"Warning: Gemini configuration failed: {e}")

def generate_ai_response(system_prompt, context, user_query, provider="google", model_name=None, api_key=None):
    # Truncate context to avoid token limits (approx 30k chars ~ 7-8k tokens, safe for flash models)
    MAX_CONTEXT_LENGTH = 30000 
    if len(context) > MAX_CONTEXT_LENGTH:
        context = context[:MAX_CONTEXT_LENGTH] + "...[truncated]"

    prompt = f"{system_prompt}\n\nContext:\n{context}\n\nUser Question: {user_query}\n\nAnswer:"
    



    if provider == "google":
        # Ensure we use a valid model name format
        base_model = model_name or 'gemini-2.0-flash'
        # Strip 'models/' if already present to avoid double prefixing
        clean_model = base_model.replace("models/", "").strip().lower()
        selected_model = f"models/{clean_model}"
        
        current_api_key = api_key or GEMINI_DEFAULT_KEY
        
        print(f"DEBUG: Using Google Provider. Requested: {selected_model}")
        if current_api_key:
            print(f"DEBUG: API Key used (prefix): {current_api_key[:8]}...")
        else:
            print("DEBUG: No API Key found in .env or request!")

        try:
            # Re-configure for every request to ensure the right key is used
            if current_api_key:
                genai.configure(api_key=current_api_key)
            
            try:
                print(f"DEBUG: Attempting AI call with {selected_model}")
                model = genai.GenerativeModel(selected_model)
                response = model.generate_content(prompt)
                return response.text
            except Exception as inner_e:
                err_msg = str(inner_e).lower()
                print(f"DEBUG: Inner AI Error: {err_msg}")
                
                # Fallback mechanism for 404 (Model Not Found) or 403 (Permission Denied/Unsupported Model)
                is_fallback_candidate = any(x in err_msg for x in ["404", "not found", "notfound", "403", "not supported"])
                
                if is_fallback_candidate and "1.5-flash" not in clean_model:
                    print(f"DEBUG: Falling back from {selected_model} to models/gemini-1.5-flash")
                    fallback_model = genai.GenerativeModel("models/gemini-1.5-flash")
                    response = fallback_model.generate_content(prompt)
                    return response.text
                raise inner_e
            
        except Exception as e:
            err_msg = str(e).lower()
            print(f"DEBUG: Final AI error msg: {err_msg}")
            
            if "429" in err_msg or "resourceexhausted" in err_msg:
                return "AI Quota Exceeded. The API key has reached its free limit. Please wait a few minutes or provide a different API key in Bot Settings."
            if "404" in err_msg or "not found" in err_msg:
                return f"Model '{selected_model}' not found or unsupported for this key. Try 'gemini-1.5-flash' which is the most compatible."
            if "403" in err_msg or "permission_denied" in err_msg:
                return "API Key Permission Denied. Ensure your API key is valid and enabled for Gemini API."
            
            return f"Thinking Error: {str(e)[:100]}..."

    elif provider == "openai":
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

    elif provider == "groq":
        selected_model = model_name or "llama3-8b-8192"
        current_api_key = api_key or GROQ_DEFAULT_KEY
        
        client = Groq(api_key=current_api_key)
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
    except Exception as e:
        return f"Error extracting PDF: {e}"

def extract_text_from_txt(file_stream) -> str:
    try:
        content = file_stream.read()
        if isinstance(content, bytes):
            return content.decode("utf-8")
        return content
    except Exception as e:
        return f"Error extracting text: {e}"
