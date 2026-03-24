import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("No GEMINI_API_KEY found in .env")
    exit(1)

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-1.5-flash')

try:
    response = model.generate_content("Say hello")
    print(f"Success: {response.text}")
except Exception as e:
    import traceback
    print(f"Error with key {api_key[:8]}...")
    traceback.print_exc()
