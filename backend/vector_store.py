"""
Pinecone Vector Store — Chunking, Embedding & Semantic Search
Handles all interactions with Pinecone for the RAG pipeline.
"""

import os
import logging
import hashlib
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────────────────
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "nimmi-knowledge-base")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Pinecone client (initialized lazily)
_pc = None
_index = None


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


# ─── Text Chunking ───────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Split text into overlapping chunks for better semantic coverage.
    
    Args:
        text: The full text to chunk.
        chunk_size: Target character count per chunk.
        overlap: Number of characters to overlap between consecutive chunks.
    
    Returns:
        A list of text chunks.
    """
    if not text or not text.strip():
        return []

    # Clean up excessive whitespace
    text = " ".join(text.split())

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size

        # Try to break at a sentence boundary (., !, ?) or newline
        if end < text_len:
            # Look for the last sentence-ending punctuation within the chunk
            best_break = -1
            for sep in [". ", "! ", "? ", "\n"]:
                pos = text.rfind(sep, start, end)
                if pos > best_break:
                    best_break = pos

            if best_break > start:
                end = best_break + 1  # Include the punctuation

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move forward with overlap
        start = end - overlap if end < text_len else text_len

    logger.info(f"[VectorStore] Chunked text into {len(chunks)} pieces (avg {sum(len(c) for c in chunks) // max(len(chunks), 1)} chars)")
    return chunks


# ─── Embedding Generation ────────────────────────────────────────

def generate_embedding(text: str) -> List[float]:
    """
    Generate a vector embedding for the given text using Gemini's embedding model.
    This is FREE within Google AI Studio limits.
    
    Returns:
        A list of floats representing the text embedding.
    """
    result = genai.embed_content(
        model="models/embedding-001",
        content=text,
        task_type="retrieval_document",
    )

    return result["embedding"]


def generate_query_embedding(query: str) -> List[float]:
    """
    Generate an embedding optimized for search queries.
    Uses task_type="retrieval_query" for better semantic matching.
    """
    import google.generativeai as genai

    genai.configure(api_key=GEMINI_API_KEY, transport="rest")

    result = genai.embed_content(
        model="models/embedding-001",
        content=query,
        task_type="retrieval_query",
    )

    return result["embedding"]


# ─── Pinecone Operations ─────────────────────────────────────────

def _make_chunk_id(bot_id: str, chunk_index: int, content: str) -> str:
    """Generate a deterministic ID for a chunk to enable idempotent upserts."""
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
    return f"{bot_id}_{chunk_index}_{content_hash}"


def upsert_knowledge(bot_id: str, text: str, source_name: str = "upload") -> int:
    """
    Chunk text, generate embeddings, and upsert into Pinecone.
    
    Args:
        bot_id: The bot this knowledge belongs to.
        text: The full extracted text.
        source_name: Label for the source (filename, URL, etc.)
    
    Returns:
        Number of chunks upserted.
    """
    index = _get_index()
    chunks = chunk_text(text)

    if not chunks:
        logger.warning(f"[VectorStore] No chunks generated for bot {bot_id}")
        return 0

    # Process in batches of 50 to stay within Pinecone limits
    batch_size = 50
    total_upserted = 0

    for batch_start in range(0, len(chunks), batch_size):
        batch_chunks = chunks[batch_start : batch_start + batch_size]
        vectors = []

        for i, chunk in enumerate(batch_chunks):
            chunk_idx = batch_start + i
            try:
                embedding = generate_embedding(chunk)
                vector_id = _make_chunk_id(bot_id, chunk_idx, chunk)
                vectors.append({
                    "id": vector_id,
                    "values": embedding,
                    "metadata": {
                        "bot_id": bot_id,
                        "source": source_name,
                        "chunk_index": chunk_idx,
                        "text": chunk[:1000],  # Pinecone metadata limit ~40KB, keep text concise
                    },
                })
            except Exception as e:
                logger.error(f"[VectorStore] Embedding error for chunk {chunk_idx}: {e}")
                continue

        if vectors:
            index.upsert(vectors=vectors, namespace=bot_id)
            total_upserted += len(vectors)
            logger.info(f"[VectorStore] Upserted batch of {len(vectors)} vectors for bot {bot_id}")

    logger.info(f"[VectorStore] Total {total_upserted} chunks indexed for bot {bot_id} from '{source_name}'")
    return total_upserted


def query_knowledge(bot_id: str, query: str, top_k: int = 5) -> List[Dict]:
    """
    Perform semantic search against a bot's knowledge base.
    
    Args:
        bot_id: The bot to search within.
        query: The user's question.
        top_k: Number of most relevant chunks to return.
    
    Returns:
        List of dicts with 'text', 'score', and 'source' fields.
    """
    index = _get_index()

    try:
        query_embedding = generate_query_embedding(query)

        results = index.query(
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
