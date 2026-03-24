import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
print(f"Testing key: {api_key[:8]}...")

try:
    genai.configure(api_key=api_key)
    # 0.3.2 usually uses 'gemini-pro' or 'models/gemini-pro'
    model = genai.GenerativeModel("gemini-pro")
    print("Attempting to generate content with gemini-pro...")
    response = model.generate_content("Hello")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Direct SDK Error: {e}")
