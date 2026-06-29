"""
Long-term per-customer memory.

Two memory types, deliberately separated:
- semantic  : durable facts about the customer (preferences, name, past issues)
- episodic  : what happened in past interactions ("asked about returns, resolved")

Why this is separate from the LangGraph checkpointer:
- Checkpointer = SHORT-TERM thread state (current conversation, resumable)
- This file  = LONG-TERM cross-session memory (persists forever, per customer)

The hard parts are not storage — they are:
1. WHEN to write a memory (not every message, only meaningful ones)
2. WHAT to write (concise, factual, no hallucinated summaries)
3. AVOIDING stale/contradictory memories (future: add a dedup step)

Interview point: most people dump everything into one vector store.
The three-type separation (short-term / semantic / episodic) is the
mature design — each type has different write frequency, retention,
and retrieval strategy.
"""
from app.db import get_pool
from app.embeddings import aembed_query, aembed_passages


async def ensure_customer(customer_id: int) -> None:
    """
    Ensure a customer row exists before reading or writing memories.
    Uses INSERT ... ON CONFLICT DO NOTHING — idempotent, safe to call every time.
    This is the upsert pattern: no race conditions, no duplicate rows.
    """
    if not customer_id:
        return
    pool = get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO customers (id, external_id)
            VALUES (%s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (customer_id, str(customer_id)),
        )


async def retrieve_memories(customer_id: int, query: str, k: int = 4) -> list[str]:
    """
    Fetch the most relevant long-term memories for this customer.

    Uses vector similarity so we get memories RELEVANT to the current
    question, not just the most recent ones.

    Example: a customer asks about 'order 123' — we surface the memory
    'Customer had a refund issue with order 123' from 3 months ago,
    even though newer memories exist about other topics.
    """
    if not customer_id:
        return []

    await ensure_customer(customer_id)

    qvec = await aembed_query(query)
    pool = get_pool()

    async with pool.connection() as conn:
        rows = await (await conn.execute(
            """
            SELECT content, 1 - (embedding <=> %s::vector) AS score
            FROM memories
            WHERE customer_id = %s
              AND embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (qvec, customer_id, qvec, k),
        )).fetchall()

    return [r["content"] for r in rows]


async def write_memory(
    customer_id: int,
    content: str,
    kind: str = "episodic",
) -> None:
    """
    Write a memory for this customer.

    We embed the content so future retrieval finds RELEVANT memories,
    not just recent ones. A memory about 'refund for order 123' will
    surface when the customer asks about order 123 again even if it
    was months ago.

    kind='episodic'  — what happened in this interaction
    kind='semantic'  — durable fact about the customer (use explicitly)
    """
    if not customer_id or not content.strip():
        return

    await ensure_customer(customer_id)

    vec = (await aembed_passages([content]))[0]
    pool = get_pool()

    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO memories (customer_id, kind, content, embedding)
            VALUES (%s, %s, %s, %s)
            """,
            (customer_id, kind, content, vec),
        )