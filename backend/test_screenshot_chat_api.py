import requests
import json

url = "http://localhost:8000/api/chat/message"
payload = {
    "bot_id": "894264ec-d748-4060-90a0-e5b50ba58eb5",
    "message": "Hello, how are you?",
    "visitor_session_id": "test-session",
    "history": []
}

try:
    response = requests.post(url, json=payload)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
