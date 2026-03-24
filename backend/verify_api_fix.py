import requests
import json

url = "http://localhost:8000/api/bots/create"
payload = {
    "user_id": "51ce6d64-445b-434b-8b91-3a883dd148f4",
    "bot_name": "Final Verification Bot",
    "system_prompt": "You are a helpful assistant.",
    "visual_config": {"color": "#3b82f6"}
}

response = requests.post(url, json=payload)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

if response.status_code == 200:
    bot_id = response.json().get("bot_id")
    # Verify we can get its config
    config_url = f"http://localhost:8000/api/bots/{bot_id}/config"
    config_response = requests.get(config_url)
    print(f"Config Status: {config_response.status_code}")
    print(f"Config: {config_response.json()}")
