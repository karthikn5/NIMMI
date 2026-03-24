import requests
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

for protocol in ["v1", "v1beta"]:
    for model in ["gemini-1.5-flash", "gemini-pro", "gemini-1.0-pro"]:
        url = f"https://generativelanguage.googleapis.com/{protocol}/models/{model}:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": "hi"}]}]}
        try:
            response = requests.post(url, json=payload)
            print(f"{protocol} - {model}: {response.status_code}")
            if response.status_code == 200:
                print(f"  SUCCESS! {response.json().get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')[:20]}")
        except: pass
