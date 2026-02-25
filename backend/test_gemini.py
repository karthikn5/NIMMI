import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

print(f"GenAI Version: {genai.__version__}")

api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
    try:
        print("\n--- Testing 'gemini-pro' ---")
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content("Hi")
        print(f"Success! Response: {response.text}")
    except Exception as e:
        print(f"Failed with 'gemini-pro': {e}")
            
    try:
        print("\n--- Testing 'models/gemini-pro' ---")
        model = genai.GenerativeModel("models/gemini-pro")
        response = model.generate_content("Hi")
        print(f"Success! Response: {response.text}")
    except Exception as e:
        print(f"Failed with 'models/gemini-pro': {e}")
