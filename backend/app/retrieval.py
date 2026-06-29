"""Hybrid retrieval: vector search + keyword search, fused with RRF.

Why hybrid and not just vector search:
- Vector search captures MEANING: 'refund' matches 'money back', 'return policy'
- Keyword search captures EXACT TERMS: order IDs, product names, version numbers
- Each catches what the other misses — combining them beats either alone

Why RRF (Reciprocal Rank Fusion) and not averaging scores:
- Vector scores and keyword scores live on completely different scales
  (cosine similarity vs ts_rank) — you can't meaningfully average them
- RRF only uses RANK position, not the score value, so scale doesn't matter
- Formula: each result gets 1/(RRF_K + rank) from each list, then sum
- RRF_K=60 is the standard constant — dampens the influence of very low ranks
"""
from app.db import get_pool
from app.embeddings import aembed_query

RRF_K = 60


async def hybrid_search(query: str, k: int = 5) -> list[dict]:
    qvec = await aembed_query(query)
    pool = get_pool()

    async with pool.connection() as conn:
        # 1. vector search — cosine distance via pgvector's <=> operator
        #    lower distance = more similar, so we convert to similarity: 1 - distance
        vec_rows = await (await conn.execute(
            """
            SELECT id, document_id, content,
                   1 - (embedding <=> %s::vector) AS score
            FROM chunks
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (qvec, qvec, k),
        )).fetchall()

        # 2. keyword search — Postgres full-text ranking
        kw_rows = await (await conn.execute(
            """
            SELECT id, document_id, content,
                   ts_rank(tsv, plainto_tsquery('english', %s)) AS score
            FROM chunks
            WHERE tsv @@ plainto_tsquery('english', %s)
            ORDER BY score DESC
            LIMIT %s
            """,
            (query, query, k),
        )).fetchall()

    # 3. RRF fusion
    fused: dict[int, dict] = {}
    for ranked in (vec_rows, kw_rows):
        for rank, row in enumerate(ranked):
            cid = row["id"]
            entry = fused.setdefault(cid, {
                "content": row["content"],
                "document_id": row["document_id"],
                "rrf": 0.0,
            })
            entry["rrf"] += 1.0 / (RRF_K + rank)

    results = sorted(fused.values(), key=lambda r: r["rrf"], reverse=True)[:k]

    # best_vector_score is used as a confidence proxy in the graph:
    # if the top vector match is weak, the answer is probably not in the KB
    best_vector_score = vec_rows[0]["score"] if vec_rows else 0.0
    for r in results:
        r["best_vector_score"] = best_vector_score

    return results