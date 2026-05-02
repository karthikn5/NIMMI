import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("GEMINI_API_KEY")
if not key:
    print("No GEMINI_API_KEY found")
else:
    print(f"Key found (starts with {key[:5]}...)")
    try:
        genai.configure(api_key=key, transport='rest')
        # Try a known good model
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content("Hello")
        print(f"Success! Response: {response.text}")
    except Exception as e:
        print(f"Failed with gemini-1.5-flash: {e}")
        
    try:
        print("Testing gemini-2.0-flash...")
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content("Hello")
        print(f"Success! Response: {response.text}")
    except Exception as e:
        print(f"Failed with gemini-2.0-flash: {e}")

    try:
        print("Testing gemini-3-flash-preview...")
        model = genai.GenerativeModel('gemini-3-flash-preview')
        response = model.generate_content("Hello")
        print(f"Success! Response: {response.text}")
    except Exception as e:
        print(f"Failed with gemini-3-flash-preview: {e}")
