import httpx
import asyncio
from bs4 import BeautifulSoup
import logging
import re
from urllib.parse import urldefrag, urljoin, urlparse

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
SKIP_EXT = re.compile(r"\.(pdf|jpe?g|png|gif|webp|svg|zip|mp4|mp3|docx?|xlsx?|pptx?|css|js|ico|xml)$", re.IGNORECASE)


def _clean_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "header", "footer", "nav", "noscript"]):
        tag.decompose()
    lines = (line.strip() for line in soup.get_text().splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    return re.sub(r"\n+", "\n", "\n".join(c for c in chunks if c))


async def _fetch(client: httpx.AsyncClient, url: str) -> tuple[str, list[str]]:
    """Page text and the links on it."""
    response = await client.get(url, headers=HEADERS)
    response.raise_for_status()
    if "html" not in response.headers.get("content-type", "html"):
        return "", []
    soup = BeautifulSoup(response.text, "html.parser")
    links = [urljoin(str(response.url), a["href"]) for a in soup.find_all("a", href=True)]
    return _clean_text(soup), links


async def extract_text_from_url(url: str) -> str:
    """
    Crawls a URL and extracts clean text content.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            text, _ = await _fetch(client, url)
            return text
    except Exception as e:
        logger.error(f"Scraping Error for {url}: {e}")
        return f"Error crawling URL: {str(e)}"


async def crawl_site(url: str, max_pages: int = 10) -> list[tuple[str, str]]:
    """
    The page at `url` plus pages it links to on the same website, up to `max_pages`.
    Returns [(page url, text)]; pages that fail or have no text are skipped.
    """
    from netsafe import UnsafeUrl, assert_public_url

    host = urlparse(url).hostname
    pages: list[tuple[str, str]] = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
        try:
            text, links = await _fetch(client, url)
        except Exception as e:
            logger.error(f"Scraping Error for {url}: {e}")
            raise
        if text:
            pages.append((url, text))
        seen = {url.rstrip("/")}
        queue = []
        for link in links:
            clean = urldefrag(link)[0].rstrip("/")
            parsed = urlparse(clean)
            if parsed.scheme in ("http", "https") and parsed.hostname == host and clean not in seen and not SKIP_EXT.search(parsed.path):
                seen.add(clean)
                queue.append(clean)
        queue = queue[: max(0, max_pages - 1)]

        limit = asyncio.Semaphore(4)

        async def one(link: str):
            async with limit:
                try:
                    safe = await assert_public_url(link)
                    page_text, _ = await _fetch(client, safe)
                    return (link, page_text) if page_text else None
                except (UnsafeUrl, Exception) as e:
                    logger.info(f"Skipped {link}: {e}")
                    return None

        for result in await asyncio.gather(*(one(link) for link in queue)):
            if result:
                pages.append(result)
    return pages

async def extract_youtube_transcript(video_id_or_url: str) -> str:
    """
    Extracts transcript from a YouTube video.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        
        # Extract video ID
        video_id = video_id_or_url
        if "youtube.com" in video_id_or_url or "youtu.be" in video_id_or_url:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", video_id_or_url)
            if match:
                video_id = match.group(1)
                
        # Run the blocking call in a thread
        transcript_list = await asyncio.to_thread(YouTubeTranscriptApi.get_transcript, video_id)
        transcript = " ".join([item['text'] for item in transcript_list])
        return transcript
        
    except Exception as e:
        logger.error(f"YouTube Transcript Error: {e}")
        return f"Error extracting YouTube transcript: {str(e)}"
