"""Local embeddings via sentence-transformers (bge-small-en-v1.5, 384-dim).

Why local and not an API: embeddings are HIGH volume (every chunk on ingest,
every query on retrieval) and quality-tolerant. Running them locally is free
and avoids per-call cost. The LLM (low-volume, quality-critical) stays on an
API. That cost split is the 'hybrid' decision worth explaining in interviews.

First call downloads the model (~130MB) -- needs internet that one time only.
encode() is CPU-bound so async callers wrap it in asyncio.to_thread().
"""
import asyncio
from functools import lru_cache

from app.config import settings

# bge models retrieve better when the QUERY gets this prefix.
# Passages (chunks) are embedded WITHOUT it. This asymmetry is intentional
# and documented in the bge paper -- it's a good interview detail.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(settings.embedding_model)


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Embed a batch of KB chunks. No prefix."""
    vecs = _model().encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def embed_query(text: str) -> list[float]:
    """Embed a single user query. With the bge prefix."""
    vec = _model().encode([QUERY_PREFIX + text], normalize_embeddings=True)[0]
    return vec.tolist()


async def aembed_passages(texts: list[str]) -> list[list[float]]:
    return await asyncio.to_thread(embed_passages, texts)


async def aembed_query(text: str) -> list[float]:
    return await asyncio.to_thread(embed_query, text)