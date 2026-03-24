import httpx
import asyncio

async def test_login():
    url = "http://localhost:8000/api/auth/login"
    payload = {
        "email": "karthikn162k3@gmail.com",
        "password": "password"  # I don't know the real password, but it should return 401 not hang
    }
    
    print(f"Sending request to {url}...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=5.0)
            print(f"Response Status: {resp.status_code}")
            print(f"Response Body: {resp.text}")
    except Exception as e:
        print(f"Request FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test_login())
