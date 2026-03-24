import requests

bot_id = "894264ec-d748-4060-90a0-e5b60ba58eb5"
url = f"http://localhost:8000/api/bots/{bot_id}"
payload = {
    "ai_api_key": "AIzaSy_TEST_KEY_123"
}

response = requests.patch(url, json=payload)
print(f"PATCH Status: {response.status_code}")
print(f"PATCH Response: {response.json()}")

if response.status_code == 200:
    # Verify it was saved
    config_url = f"http://localhost:8000/api/bots/{bot_id}/config"
    config_response = requests.get(config_url)
    print(f"Config API Key: {config_response.json().get('ai_api_key')}")
