import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

def list_default_models():
    key = os.getenv("GEMINI_API_KEY")
    print(f"Listing models for Default Key: {key[:10]}...")
    genai.configure(api_key=key, transport='rest')
    for m in genai.list_models():
        print(f"Model: {m.name}")

if __name__ == "__main__":
    list_default_models()
