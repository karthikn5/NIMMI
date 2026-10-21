"""
Pinecone vector store: chunking, embedding and semantic search for large knowledge bases.

Small knowledge is read in full by the assistant (brain.py); this index is what finds the right
passages when a business's knowledge is too big for that. Embeddings use Gemini's REST API in
batches of 100, and replace_knowledge() rebuilds a bot's whole index so no outdated text lingers.
"""
import asyncio
import hashlib
import logging
import os
import re
from typing import Dict, List, Tuple

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────────────────
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "nimmi-knowledge-base")
EMBED_MODEL = "gemini-embedding-001"
EMBED_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{EMBED_MODEL}"
CHUNK_SIZE, CHUNK_OVERLAP = 1200, 150
PAGE_HEADING = re.compile(r"^## (https?://\S+.*)$", re.MULTILINE)  # pages of a website source

_pc = None
_index = None
_dimension = None


def _get_index():
    """Lazily initialize and return the Pinecone index."""
    global _pc, _index
    if _index is not None:
        return _index
    if not PINECONE_API_KEY:
        raise RuntimeError("PINECONE_API_KEY is not set in environment variables")
    from pinecone import Pinecone
    _pc = Pinecone(api_key=PINECONE_API_KEY)
    _index = _pc.Index(PINECONE_INDEX_NAME)
    logger.info(f"[VectorStore] Connected to Pinecone index: {PINECONE_INDEX_NAME}")
    return _index


def _index_dimension() -> int:
    """The vector size the index stores; gemini-embedding-001 can make 768, 1536 or 3072."""
    global _dimension
    if _dimension is None:
        try:
            _dimension = int(_get_index().describe_index_stats().get("dimension") or 0) or None
        except Exception as e:
            logger.warning(f"[VectorStore] Couldn't read the index size: {e}")
        if _dimension is None:
            return int(os.getenv("EMBED_DIMENSIONS", "768"))
    return _dimension


# ─── Text chunking ───────────────────────────────────────────────
def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Overlapping pieces of about `chunk_size` characters, broken at sentence ends where possible."""
    if not text or not text.strip():
        return []
    text = " ".join(text.split())
    chunks, start, n = [], 0, len(text)
    while start < n:
        end = start + chunk_size
        if end < n:
            best = max(text.rfind(sep, start + chunk_size // 2, end) for sep in (". ", "! ", "? ", "; "))
            if best > start:
                end = best + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap if end < n else n
    return chunks


# ─── Embeddings (Gemini REST) ────────────────────────────────────
def _key() -> str:
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return key


def embed_batch(texts: List[str], task: str = "RETRIEVAL_DOCUMENT") -> List[List[float]]:
    """Embeddings for up to 100 texts in one request."""
    size = _index_dimension()
    body = {"requests": [{"model": f"models/{EMBED_MODEL}", "content": {"parts": [{"text": t}]}, "taskType": task,
                          "outputDimensionality": size} for t in texts]}
    r = httpx.post(f"{EMBED_URL}:batchEmbedContents", headers={"x-goog-api-key": _key()}, json=body, timeout=60)
    r.raise_for_status()
    return [e["values"] for e in r.json()["embeddings"]]


def generate_embedding(text: str) -> List[float]:
    return embed_batch([text])[0]


def generate_query_embedding(query: str) -> List[float]:
    return embed_batch([query], task="RETRIEVAL_QUERY")[0]


# ─── Pinecone operations ─────────────────────────────────────────
def _make_chunk_id(bot_id: str, chunk_index: int, content: str) -> str:
    """Deterministic ID for a chunk, so the same text upserts idempotently."""
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
    return f"{bot_id}_{chunk_index}_{content_hash}"


def _store(bot_id: str, pieces: List[Tuple[str, str]]) -> int:
    """Embed (in batches of 100) and store (source, passage) pairs in the bot's namespace."""
    index = _get_index()
    total = 0
    for start in range(0, len(pieces), 100):
        batch = pieces[start:start + 100]
        try:
            vectors = embed_batch([chunk for _, chunk in batch])
        except Exception as e:
            logger.error(f"[VectorStore] Embedding batch failed for bot {bot_id}: {e}")
            continue
        index.upsert(vectors=[{
            "id": _make_chunk_id(bot_id, start + i, chunk), "values": values,
            "metadata": {"bot_id": bot_id, "source": source[:300], "chunk_index": start + i, "text": chunk[:1500]},
        } for i, ((source, chunk), values) in enumerate(zip(batch, vectors))], namespace=bot_id)
        total += len(batch)
    logger.info(f"[VectorStore] Indexed {total} passages for bot {bot_id}")
    return total


def upsert_knowledge(bot_id: str, text: str, source_name: str = "upload") -> int:
    """Chunk, embed and store `text` in the bot's namespace. Returns passages stored."""
    return _store(bot_id, [(source_name, chunk) for chunk in chunk_text(text)])


def _sections(text: str) -> List[Tuple[str, str]]:
    """(source, text) for the written knowledge, each source and each page of a website, so every
    passage found in a search says where it came from."""
    import knowledge_sources
    written, blocks = knowledge_sources.split(text)
    out = [("Written knowledge", written)] if written else []
    for name, body in blocks:
        if name == knowledge_sources.SUMMARY:
            continue  # the assistant always reads the summary (brain.knowledge)
        parts = PAGE_HEADING.split(body)
        if len(parts) == 1:
            out.append((name, body))
            continue
        if parts[0].strip():
            out.append((name, parts[0]))
        out += [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts), 2)]
    return out


def replace_knowledge(bot_id: str, text: str) -> int:
    """Rebuild a bot's whole index from its current knowledge, so removed or changed text can't linger."""
    delete_bot_knowledge(bot_id)
    return _store(bot_id, [(source, chunk) for source, body in _sections(text or "") for chunk in chunk_text(body)])


async def query_knowledge(bot_id: str, query: str, top_k: int = 5) -> List[Dict]:
    """
    Perform semantic search against a bot's knowledge base.
    
    Args:
        bot_id: The bot to search within.
        query: The user's question.
        top_k: Number of most relevant chunks to return.
    
    Returns:
        List of dicts with 'text', 'score', and 'source' fields.
    """
    try:
        # Connecting, embedding and querying are blocking calls: keep them off the event loop.
        index = await asyncio.to_thread(_get_index)
        query_embedding = await asyncio.wait_for(
            asyncio.to_thread(generate_query_embedding, query),
            timeout=10.0
        )

        results = await asyncio.to_thread(
            index.query,
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True,
            namespace=bot_id,
        )

        matches = []
        for match in results.get("matches", []):
            metadata = match.get("metadata", {})
            matches.append({
                "text": metadata.get("text", ""),
                "score": match.get("score", 0),
                "source": metadata.get("source", "unknown"),
            })

        logger.info(f"[VectorStore] Query for bot {bot_id}: found {len(matches)} matches (top score: {matches[0]['score'] if matches else 'N/A'})")
        return matches

    except Exception as e:
        logger.error(f"[VectorStore] Query error for bot {bot_id}: {e}")
        return []


async def warm_up() -> None:
    """Open the Pinecone connection at startup so the first visitor doesn't wait for it."""
    try:
        await asyncio.to_thread(_get_index)
    except Exception as e:
        logger.warning(f"[VectorStore] Warm-up skipped: {e}")


def delete_bot_knowledge(bot_id: str) -> bool:
    """
    Delete all vectors for a specific bot from Pinecone.
    Called when a bot is deleted or knowledge is reset.
    """
    try:
        index = _get_index()
        index.delete(delete_all=True, namespace=bot_id)
        logger.info(f"[VectorStore] Deleted all vectors for bot {bot_id}")
        return True
    except Exception as e:
        logger.error(f"[VectorStore] Delete error for bot {bot_id}: {e}")
        return False


def get_bot_vector_count(bot_id: str) -> int:
    """Get the number of vectors stored for a bot."""
    try:
        index = _get_index()
        stats = index.describe_index_stats()
        namespaces = stats.get("namespaces", {})
        ns_info = namespaces.get(bot_id, {})
        return ns_info.get("vector_count", 0)
    except Exception as e:
        logger.error(f"[VectorStore] Stats error for bot {bot_id}: {e}")
        return 0
