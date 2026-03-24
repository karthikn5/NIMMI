import requests

url = "http://localhost:8000/api/bots/create"
payload = {
    "user_id": "23984ca3-48fb-4fd4-ac0e-749e77b6706e",
    "bot_name": "New Account Bot",
    "system_prompt": "You are a helpful assistant.",
    "visual_config": {"color": "#3b82f6"}
}

response = requests.post(url, json=payload)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
