import asyncio
import httpx
from bs4 import BeautifulSoup
import re

async def extract_text_from_url(url: str) -> str:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            print(f"Fetching {url}...")
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            for script in soup(["script", "style", "header", "footer", "nav"]):
                script.decompose()
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            text = re.sub(r'\n+', '\n', text)
            return text
    except Exception as e:
        return f"Error: {e}"

async def main():
    url = "https://example.com"
    result = await extract_text_from_url(url)
    print(f"Result length: {len(result)}")
    print(f"Preview: {result[:100]}...")

if __name__ == "__main__":
    asyncio.run(main())
