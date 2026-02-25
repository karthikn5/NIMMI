import requests
import os
from dotenv import load_dotenv
import json

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

print("--- Listing Models ---")
url_list = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
try:
    r = requests.get(url_list)
    if r.status_code == 200:
        models = r.json().get('models', [])
        for m in models:
            if 'generateContent' in m.get('supportedGenerationMethods', []):
                print(f" - {m['name']}")
    else:
        print(f"List failed: {r.status_code} {r.text}")
except Exception as e:
    print(f"List Error: {e}")

print("\n--- Testing gemini-pro ---")
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={api_key}"
payload = {"contents": [{"parts": [{"text": "Hello"}]}]}
headers = {'Content-Type': 'application/json'}
try:
    r = requests.post(url, headers=headers, json=payload)
    print(f"Status: {r.status_code}")
    if r.status_code != 200:
        print(r.text)
    else:
        print("Success!")
except Exception as e:
    print(f"Error: {e}")
