import httpx
import asyncio
import sys

async def test_login():
    url = "http://localhost:8000/api/auth/login"
    payload = {
        "email": "karthikn162k3@gmail.com",
        "password": "password"
    }
    
    print(f"Sending POST to {url}...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10.0)
            print(f"Status Code: {resp.status_code}")
            print(f"Body: {resp.text}")
    except httpx.ConnectError:
        print("FAILED: Connection Error (Is the server running?)")
    except httpx.TimeoutException:
        print("FAILED: Timeout (Is the server hanging?)")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_login())
