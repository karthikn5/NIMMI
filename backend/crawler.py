import httpx
import asyncio
from bs4 import BeautifulSoup
import logging
import re

logger = logging.getLogger(__name__)

async def extract_text_from_url(url: str) -> str:
    """
    Crawls a URL and extracts clean text content.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "header", "footer", "nav"]):
                script.decompose()
                
            # Get text
            text = soup.get_text()
            
            # Break into lines and remove leading/trailing whitespace
            lines = (line.strip() for line in text.splitlines())
            # Break multi-headlines into a line each
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            # Drop blank lines
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            # Basic cleanup of extra whitespace
            text = re.sub(r'\n+', '\n', text)
            
            return text
            
    except Exception as e:
        logger.error(f"Scraping Error for {url}: {e}")
        return f"Error crawling URL: {str(e)}"

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
