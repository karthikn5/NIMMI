import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as client:
        try:
            # We use a random UUID to see if the server responds
            resp = await client.get("http://localhost:8000/api/bots/00000000-0000-0000-0000-000000000000/config")
            print(f"Status: {resp.status_code}")
            print(f"Body: {resp.text}")
        except Exception as e:
            print(f"FAILED to reach backend: {e}")

asyncio.run(test())
