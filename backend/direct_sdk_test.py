import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
print(f"Testing key: {api_key[:8]}...")

try:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    print("Attempting to generate content...")
    response = model.generate_content("Hello, say 'API is working'")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Direct SDK Error: {e}")
